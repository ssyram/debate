{-# LANGUAGE MultiWayIf #-}
{-# LANGUAGE LambdaCase #-}
module Types
  ( -- * Monad stack
    AppM
  , runAppM
    -- * Config
  , Config(..)
  , defaultConfig
    -- * Errors
  , AppError(..)
  , throwApp
    -- * Check domain
  , Proposition(..)
  , Severity(..)
  , Issue(..)
  , IssueType(..)
  , DesignPoint(..)
  , CoverageCell(..)
  , CoverageStatus(..)
  , SuspiciousClaim(..)
  , QAFeedback(..)
  , qaFeedbackId
  , CheckReport(..)
  , emptyCheckReport
  , okToGo
    -- * Polish domain
  , Design
  , RewriteGuide
  , noNewGuide
  , emptyGuide
  , combineCheckAndGuide
    -- * Logging
  , LogEvent(..)
  ) where

import Control.Monad.Reader
import Control.Monad.Except
import Data.Text (Text)
import qualified Data.Text as T
import GHC.Generics (Generic)
import Data.Aeson (FromJSON(..), ToJSON(..), withText, withObject, (.:), (.:?), (.!=), object, (.=), Object)
import Data.Aeson.Types (Parser)

-- ────────────────────────────────────────────────────────────────────
-- Monad stack: ReaderT Config (ExceptT AppError IO)
-- ────────────────────────────────────────────────────────────────────

type AppM = ReaderT Config (ExceptT AppError IO)

runAppM :: Config -> AppM a -> IO (Either AppError a)
runAppM cfg = runExceptT . flip runReaderT cfg

throwApp :: AppError -> AppM a
throwApp = throwError

-- ────────────────────────────────────────────────────────────────────
-- Config
-- ────────────────────────────────────────────────────────────────────

data Config = Config
  { cfgBaseUrl          :: Text      -- ^ OpenAI-compatible endpoint (full URL to /chat/completions)
  , cfgApiKey           :: Text      -- ^ Bearer token
  , cfgModel            :: Text      -- ^ Model name
  , cfgMaxRewriteRounds :: Int       -- ^ Inner rewrite loop cap
  , cfgMaxPolishRounds  :: Int       -- ^ Outer polish loop cap
  , cfgTimeoutSeconds   :: Int       -- ^ HTTP timeout
  , cfgMaxTokens        :: Int       -- ^ max_tokens for LLM calls
  , cfgTemperature      :: Double    -- ^ temperature
  , cfgVerbose          :: Bool
  , cfgOutputDir        :: FilePath  -- ^ Where artifacts go
  -- | debate-tool log file — always present.
  -- topic mode:  outDir/<stem>_log.json  (written by debate-tool run)
  -- log mode:    the supplied log.json
  , cfgLogFile          :: FilePath
  , cfgTopicFile        :: Maybe FilePath  -- ^ topic .md (only needed for fresh run)
  , cfgDesignFile       :: Maybe FilePath  -- ^ Shortcut: skip debate-tool run/resume for design
  , cfgDecisionFile     :: Maybe FilePath  -- ^ Shortcut: skip check+debate for decisions
  , cfgIssuesFile       :: Maybe FilePath  -- ^ Shortcut: skip check, use pre-computed issues
  } deriving stock (Show)

defaultConfig :: Config
defaultConfig = Config
  { cfgBaseUrl          = ""
  , cfgApiKey           = ""
  , cfgModel            = "gpt-5.4-nano"
  , cfgMaxRewriteRounds = 2
  , cfgMaxPolishRounds  = 3
  , cfgTimeoutSeconds   = 300
  , cfgMaxTokens        = 8000
  , cfgTemperature      = 0.7
  , cfgVerbose          = False
  , cfgOutputDir        = "./out"
  , cfgLogFile          = "./debate_log.json"
  , cfgTopicFile        = Nothing
  , cfgDesignFile       = Nothing
  , cfgDecisionFile     = Nothing
  , cfgIssuesFile       = Nothing
  }

-- ────────────────────────────────────────────────────────────────────
-- Errors
-- ────────────────────────────────────────────────────────────────────

data AppError
  = MissingEnvVar Text
  | FileReadError FilePath Text
  | HttpError Int Text           -- ^ status code + body
  | HttpException Text           -- ^ connection / timeout
  | JsonDecodeError Text         -- ^ aeson parse failure
  | InvalidLlmResponse Text      -- ^ non-JSON or empty
  | CannotFindDesign
  | CannotFindDecisionFile
  | MaxPolishRoundsReached
  | UserError Text
  deriving stock (Show)

-- ────────────────────────────────────────────────────────────────────
-- Check domain types
-- ────────────────────────────────────────────────────────────────────

data Severity = Low | Medium | High | Critical
  deriving stock (Show, Eq, Ord, Generic)

instance FromJSON Severity where
  parseJSON = withText "Severity" $ \case
    "low"      -> pure Low
    "medium"   -> pure Medium
    "high"     -> pure High
    "critical" -> pure Critical
    _          -> pure Medium  -- graceful fallback

instance ToJSON Severity where
  toJSON Low      = "low"
  toJSON Medium   = "medium"
  toJSON High     = "high"
  toJSON Critical = "critical"

data Proposition = Proposition
  { propId      :: Text
  , propSection :: Text
  , propText    :: Text
  } deriving stock (Show, Generic)

instance FromJSON Proposition where
  parseJSON = withObject "Proposition" $ \o ->
    Proposition <$> o .: "id" <*> o .: "section" <*> o .: "text"

instance ToJSON Proposition where
  toJSON Proposition{..} = object ["id" .= propId, "section" .= propSection, "text" .= propText]

data IssueType = Contradiction | Omission | MatrixGap
  deriving stock (Show, Generic)

instance FromJSON IssueType where
  parseJSON = withText "IssueType" $ \case
    "contradiction" -> pure Contradiction
    "omission"      -> pure Omission
    "matrix_gap"    -> pure MatrixGap
    _               -> pure Omission

instance ToJSON IssueType where
  toJSON Contradiction = "contradiction"
  toJSON Omission      = "omission"
  toJSON MatrixGap     = "matrix_gap"

data Issue = Issue
  { issueType     :: IssueType
  , issueSeverity :: Severity
  , issueRefs     :: [Text]       -- ^ Px, Py references
  , issueDesc     :: Text
  } deriving stock (Show, Generic)

instance FromJSON Issue where
  parseJSON = withObject "Issue" $ \o ->
    Issue <$> o .: "type" <*> o .: "severity" <*> o .:? "refs" .!= [] <*> o .: "description"

instance ToJSON Issue where
  toJSON Issue{..} = object
    ["type" .= issueType, "severity" .= issueSeverity, "refs" .= issueRefs, "description" .= issueDesc]

data DesignPoint = DesignPoint
  { dpId    :: Text
  , dpTitle :: Text
  } deriving stock (Show, Generic)

instance FromJSON DesignPoint where
  parseJSON = withObject "DesignPoint" $ \o -> DesignPoint <$> o .: "id" <*> o .: "title"

instance ToJSON DesignPoint where
  toJSON DesignPoint{..} = object ["id" .= dpId, "title" .= dpTitle]

data CoverageStatus = Covered | Weak | Gap
  deriving stock (Show, Eq, Generic)

instance FromJSON CoverageStatus where
  parseJSON = withText "CoverageStatus" $ \case
    "covered" -> pure Covered
    "weak"    -> pure Weak
    "gap"     -> pure Gap
    _         -> pure Gap

instance ToJSON CoverageStatus where
  toJSON Covered = "covered"
  toJSON Weak    = "weak"
  toJSON Gap     = "gap"

data CoverageCell = CoverageCell
  { ccPointA  :: Text
  , ccPointB  :: Text
  , ccStatus  :: CoverageStatus
  , ccComment :: Text
  } deriving stock (Show, Generic)

instance FromJSON CoverageCell where
  parseJSON = withObject "CoverageCell" $ \o ->
    CoverageCell <$> o .: "point_a" <*> o .: "point_b" <*> o .: "status" <*> o .:? "comment" .!= ""

instance ToJSON CoverageCell where
  toJSON CoverageCell{..} = object
    ["point_a" .= ccPointA, "point_b" .= ccPointB, "status" .= ccStatus, "comment" .= ccComment]

-- | A claim in the design that lacks sufficient supporting evidence.
data SuspiciousClaim = SuspiciousClaim
  { scId       :: Text   -- ^ e.g. "SC1"
  , scClaim    :: Text   -- ^ the verbatim or paraphrased claim
  , scLocation :: Text   -- ^ section / paragraph where the claim appears
  , scReason   :: Text   -- ^ why it's considered unsupported
  } deriving stock (Show, Generic)

instance FromJSON SuspiciousClaim where
  parseJSON = withObject "SuspiciousClaim" $ \o ->
    SuspiciousClaim <$> o .: "id" <*> o .: "claim" <*> o .: "location" <*> o .: "reason"

instance ToJSON SuspiciousClaim where
  toJSON SuspiciousClaim{..} = object
    ["id" .= scId, "claim" .= scClaim, "location" .= scLocation, "reason" .= scReason]

-- | Feedback on an existing Q&A entry from a previous polish round.
data QAFeedback
  = QAStillValid  Text Text  -- ^ qa_id, comment ("still needed, justification holds")
  | QARedundant   Text Text  -- ^ qa_id, reason ("claim now fully supported in body")
  | QAStillWeak   Text Text  -- ^ qa_id, reason ("justification still insufficient")
  deriving stock (Show, Generic)

qaFeedbackId :: QAFeedback -> Text
qaFeedbackId (QAStillValid i _) = i
qaFeedbackId (QARedundant  i _) = i
qaFeedbackId (QAStillWeak  i _) = i

instance FromJSON QAFeedback where
  parseJSON = withObject "QAFeedback" parseQAFeedback

parseQAFeedback :: Object -> Parser QAFeedback
parseQAFeedback o = do
  verdict <- o .: "verdict"
  qid <- o .: "qa_id"
  reason <- o .: "reason"
  pure (qaFeedbackFromVerdict verdict qid reason)

qaFeedbackFromVerdict :: Text -> Text -> Text -> QAFeedback
qaFeedbackFromVerdict "redundant" = QARedundant
qaFeedbackFromVerdict "still_weak" = QAStillWeak
qaFeedbackFromVerdict _ = QAStillValid

instance ToJSON QAFeedback where
  toJSON (QAStillValid i r) = object ["verdict" .= ("valid"     :: Text), "qa_id" .= i, "reason" .= r]
  toJSON (QARedundant  i r) = object ["verdict" .= ("redundant" :: Text), "qa_id" .= i, "reason" .= r]
  toJSON (QAStillWeak  i r) = object ["verdict" .= ("still_weak":: Text), "qa_id" .= i, "reason" .= r]

data CheckReport = CheckReport
  { crPropositions     :: [Proposition]
  , crIssues           :: [Issue]
  , crDesignPoints     :: [DesignPoint]
  , crMatrix           :: [CoverageCell]
  , crSuspiciousClaims :: [SuspiciousClaim]  -- ^ Phase 5: unsupported assertions
  , crQAFeedback       :: [QAFeedback]       -- ^ Phase 5: feedback on existing Q&A entries
  , crSummary          :: Text
  , crHighlights       :: [Text]
  } deriving stock (Show)

emptyCheckReport :: CheckReport
emptyCheckReport = CheckReport [] [] [] [] [] [] "" []

-- | A check is "ok to go" when there are no High or Critical severity issues
-- and no suspicious claims remain unaddressed.
okToGo :: CheckReport -> Bool
okToGo cr = not (any (\i -> issueSeverity i >= High) (crIssues cr))
          && null (crSuspiciousClaims cr)

-- ────────────────────────────────────────────────────────────────────
-- Polish domain types
-- ────────────────────────────────────────────────────────────────────

type Design = Text
type RewriteGuide = Text

noNewGuide :: RewriteGuide -> Bool
noNewGuide g = T.null (T.strip g) || T.strip g == "none" || T.strip g == "no_changes"

emptyGuide :: RewriteGuide
emptyGuide = ""

-- | When max rewrite rounds hit, combine unresolved check + remaining guide
combineCheckAndGuide :: CheckReport -> RewriteGuide -> CheckReport
combineCheckAndGuide cr guide
  | noNewGuide guide = cr
  | otherwise = cr { crSummary = crSummary cr <> "\n\n## Unresolved Rewrite Guide\n\n" <> guide }

-- ────────────────────────────────────────────────────────────────────
-- Logging events
-- ────────────────────────────────────────────────────────────────────

data LogEvent
  = StartPolish
  | NewPolishLoopRound Int
  | EndPolishLoop
  | StartRewrite
  | NewRewriteRound Int
  | NewRewriteGuide RewriteGuide
  | MaxRewriteRoundsReached
  | StartCheck
  | StartCheckPhase Int
  | EndCheckPhase Int
  | CheckComplete
  | DebateToolRun FilePath        -- ^ debate-tool run <topic> --output <log>
  | DebateToolResume FilePath     -- ^ debate-tool resume <log>
  | DebateToolCompact FilePath    -- ^ debate-tool compact <log>
  | MergeStart
  | MergeComplete
  | RewriteDesignStart
  | RewriteDesignComplete
  | Info Text
  | Warn Text
  | Err Text
  deriving stock (Show)
