{-# LANGUAGE LambdaCase #-}
module Llm
  ( chat
  , chatRaw
  , checkPhase1
  , checkPhase2
  , checkPhase3
  , checkPhase4
  , checkPhase5
  , Phase3Result(..)
  , Phase4Result(..)
  , Phase5Result(..)
  , rewriteDesign
  , mergeCheckAndDecisions
  , MergeResult(..)
  ) where

import Control.Monad.Except (throwError)
import Control.Monad.IO.Class (liftIO)
import Control.Monad.Reader (asks)
import qualified Control.Exception as E
import Data.Aeson (FromJSON, ToJSON(..), Value, eitherDecodeStrict, encode, object, (.=))
import qualified Data.Aeson as Aeson
import qualified Data.Aeson.Key as Key
import qualified Data.Aeson.KeyMap as KM
import Data.ByteString (ByteString)
import qualified Data.ByteString.Lazy as LBS
import Data.Text (Text)
import qualified Data.Text as T
import Data.Text.Encoding (decodeUtf8, encodeUtf8)
import qualified Data.Vector as V
import Network.HTTP.Client
import Network.HTTP.Client.TLS (tlsManagerSettings)
import Network.HTTP.Types.Header (Header)
import Network.HTTP.Types.Status (statusCode)

import Log (logEvent, logInfo)
import Prompt
import Types

newManager' :: Int -> IO Manager
newManager' timeoutSec = newManager tlsManagerSettings
  { managerResponseTimeout = responseTimeoutMicro (timeoutSec * 1000000) }

chatRaw :: Text -> AppM Text
chatRaw prompt = do
  request <- buildChatRequest prompt
  timeoutS <- asks cfgTimeoutSeconds
  manager <- liftIO $ newManager' timeoutS
  sendRequest manager request >>= extractResponseBody

buildChatRequest :: Text -> AppM Request
buildChatRequest prompt = do
  baseUrl <- asks cfgBaseUrl
  apiKey <- asks cfgApiKey
  model <- asks cfgModel
  maxTok <- asks cfgMaxTokens
  temp <- asks cfgTemperature
  initReq <- liftIO $ parseRequest (T.unpack baseUrl)
  pure $ buildRequest baseUrl apiKey model maxTok temp prompt initReq

buildRequest :: Text -> Text -> Text -> Int -> Double -> Text -> Request -> Request
buildRequest _ apiKey model maxTok temp prompt initReq = initReq
  { method = "POST"
  , requestBody = RequestBodyLBS (requestBodyJson model maxTok temp prompt)
  , requestHeaders = requestHeadersFor apiKey
  }

requestBodyJson :: Text -> Int -> Double -> Text -> LBS.ByteString
requestBodyJson model maxTok temp prompt = encode $ object
  [ "model" .= model
  , "messages" .= [object ["role" .= ("user" :: Text), "content" .= prompt]]
  , "max_tokens" .= maxTok
  , "temperature" .= temp
  ]

requestHeadersFor :: Text -> [Header]
requestHeadersFor apiKey =
  [ ("Authorization", "Bearer " <> encodeUtf8 apiKey)
  , ("Content-Type", "application/json")
  ]

sendRequest :: Manager -> Request -> AppM (Response LBS.ByteString)
sendRequest manager request = do
  result <- liftIO $ E.try @E.SomeException (httpLbs request manager)
  either (throwError . HttpException . T.pack . show) pure result

extractResponseBody :: Response LBS.ByteString -> AppM Text
extractResponseBody resp =
  if isSuccessStatus resp then extractContent body else throwHttpBody resp body
  where
    body = responseBodyStrict resp

responseBodyStrict :: Response LBS.ByteString -> ByteString
responseBodyStrict = LBS.toStrict . responseBody

isSuccessStatus :: Response body -> Bool
isSuccessStatus resp = is2xxStatus (statusCode (responseStatus resp))

is2xxStatus :: Int -> Bool
is2xxStatus status = status >= 200 && status < 300

throwHttpBody :: Response body -> ByteString -> AppM a
throwHttpBody resp body = throwError $ HttpError (statusCode (responseStatus resp)) (decodeUtf8 body)

extractContent :: ByteString -> AppM Text
extractContent bs = do
  value <- decodeJsonValue bs
  choice <- lookupChoices value
  message <- lookupMessage choice
  lookupContent message

decodeJsonValue :: ByteString -> AppM Value
decodeJsonValue bs = either (throwError . JsonDecodeError . T.pack) pure (eitherDecodeStrict bs)

lookupChoices :: Value -> AppM Value
lookupChoices value = lookupObjectField "choices" value >>= ensureNonEmptyArray "missing or empty choices array"

lookupMessage :: Value -> AppM Value
lookupMessage = lookupObjectField "message"

lookupContent :: Value -> AppM Text
lookupContent = lookupTextField "content"

lookupObjectField :: Text -> Value -> AppM Value
lookupObjectField key value = ensureObject value >>= maybeMissing key . KM.lookup (Key.fromText key)

lookupTextField :: Text -> Value -> AppM Text
lookupTextField key value = lookupObjectField key value >>= ensureText key

ensureObject :: Value -> AppM Aeson.Object
ensureObject = \case
  Aeson.Object obj -> pure obj
  _ -> throwError (InvalidLlmResponse "response is not an object")

ensureNonEmptyArray :: Text -> Value -> AppM Value
ensureNonEmptyArray msg = \case
  Aeson.Array arr | not (V.null arr) -> pure (V.head arr)
  _ -> throwError (InvalidLlmResponse msg)

ensureText :: Text -> Value -> AppM Text
ensureText _ = \case
  Aeson.String txt -> pure txt
  _ -> throwError (InvalidLlmResponse "missing content in message")

maybeMissing :: Text -> Maybe Value -> AppM Value
maybeMissing key = maybe (throwError (InvalidLlmResponse (missingFieldMessage key))) pure

missingFieldMessage :: Text -> Text
missingFieldMessage "choices" = "missing or empty choices array"
missingFieldMessage "message" = "missing message in choice"
missingFieldMessage "content" = "missing content in message"
missingFieldMessage key = "missing field: " <> key

chat :: FromJSON a => Text -> AppM a
chat prompt = do
  raw <- chatRaw prompt
  decodeChatJson raw

decodeChatJson :: FromJSON a => Text -> AppM a
decodeChatJson raw =
  either throwChatDecodeError pure (eitherDecodeStrict (encodeUtf8 (stripCodeFences raw)))
  where
    throwChatDecodeError err = throwError $ JsonDecodeError (chatDecodeMessage err raw)

chatDecodeMessage :: String -> Text -> Text
chatDecodeMessage err raw = T.pack err <> "\n\nRaw response:\n" <> T.take 500 raw

stripCodeFences :: Text -> Text
stripCodeFences t =
  if hasOpeningFence strippedText then stripFenceBody strippedText else strippedText
  where
    strippedText = T.strip t

hasOpeningFence :: Text -> Bool
hasOpeningFence = T.isPrefixOf "```"

stripFenceBody :: Text -> Text
stripFenceBody = T.strip . dropClosingFence . dropOpeningFence

dropOpeningFence :: Text -> Text
dropOpeningFence = T.drop 1 . T.dropWhile (/= '\n')

dropClosingFence :: Text -> Text
dropClosingFence txt = case T.breakOnEnd "```" txt of
  ("", _) -> txt
  (before, _) -> T.dropEnd 3 before

checkPhase1 :: Text -> AppM [Proposition]
checkPhase1 design = runCheckPhase 1 "Phase 1: 命题抽取" (chat (phase1Prompt design))

checkPhase2 :: Text -> Text -> AppM [Issue]
checkPhase2 design propsJson = runCheckPhase 2 "Phase 2: 矛盾与遗漏检查" (chat (phase2Prompt design propsJson))

data Phase3Result = Phase3Result
  { p3DesignPoints :: [DesignPoint]
  , p3Matrix :: [CoverageCell]
  } deriving stock (Show)

instance FromJSON Phase3Result where
  parseJSON = Aeson.withObject "Phase3Result" $ \o ->
    Phase3Result <$> o Aeson..: "design_points" <*> o Aeson..: "matrix"

instance ToJSON Phase3Result where
  toJSON Phase3Result{..} = object ["design_points" .= p3DesignPoints, "matrix" .= p3Matrix]

checkPhase3 :: Text -> Text -> AppM Phase3Result
checkPhase3 design propsJson = runCheckPhase 3 "Phase 3: 交叉覆盖矩阵" (chat (phase3Prompt design propsJson))

data Phase4Result = Phase4Result
  { p4Summary :: Text
  , p4Highlights :: [Text]
  } deriving stock (Show)

instance FromJSON Phase4Result where
  parseJSON = Aeson.withObject "Phase4Result" $ \o ->
    Phase4Result <$> o Aeson..: "summary" <*> o Aeson..:? "highlights" Aeson..!= []

instance ToJSON Phase4Result where
  toJSON Phase4Result{..} = object ["summary" .= p4Summary, "highlights" .= p4Highlights]

checkPhase4 :: Text -> Text -> Text -> Text -> AppM Phase4Result
checkPhase4 design propsJson issuesJson matrixJson =
  runCheckPhase 4 "Phase 4: 总结" (chat (phase4Prompt design propsJson issuesJson matrixJson))

runCheckPhase :: Int -> Text -> AppM a -> AppM a
runCheckPhase n desc action = do
  logEvent (StartCheckPhase n)
  logInfo desc
  result <- action
  logEvent (EndCheckPhase n)
  pure result

rewriteDesign :: Design -> RewriteGuide -> AppM Design
rewriteDesign design guide = do
  logEvent RewriteDesignStart
  result <- chatRaw (rewritePrompt design guide)
  logEvent RewriteDesignComplete
  pure result

data MergeResult = MergeResult
  { mrNewGuide :: RewriteGuide
  , mrUnresolvedIssues :: [Issue]
  } deriving stock (Show)

instance FromJSON MergeResult where
  parseJSON = Aeson.withObject "MergeResult" $ \o ->
    MergeResult <$> o Aeson..: "new_guide" <*> o Aeson..:? "unresolved_issues" Aeson..!= []

mergeCheckAndDecisions :: Design -> Text -> Text -> Text -> AppM MergeResult
mergeCheckAndDecisions design decisions newCheck oldCheck = do
  logEvent MergeStart
  result <- chat (mergePrompt design decisions newCheck oldCheck)
  logEvent MergeComplete
  pure result

data Phase5Result = Phase5Result
  { p5SuspiciousClaims :: [SuspiciousClaim]
  , p5QAFeedback       :: [QAFeedback]
  } deriving stock (Show)

instance FromJSON Phase5Result where
  parseJSON = Aeson.withObject "Phase5Result" $ \o ->
    Phase5Result
      <$> o Aeson..:? "suspicious_claims" Aeson..!= []
      <*> o Aeson..:? "qa_feedback"       Aeson..!= []

instance ToJSON Phase5Result where
  toJSON Phase5Result{..} = object
    ["suspicious_claims" .= p5SuspiciousClaims, "qa_feedback" .= p5QAFeedback]

checkPhase5 :: Text -> AppM Phase5Result
checkPhase5 design =
  runCheckPhase 5 "Phase 5: 可疑断言 + Q&A 审查" (chat (phase5Prompt design))
