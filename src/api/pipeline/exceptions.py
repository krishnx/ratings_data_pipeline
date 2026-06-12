class PipelineError(Exception):
    """Base class for all pipeline errors."""


class MissingSheetError(PipelineError):
    """Raised when the MASTER sheet is absent from a workbook."""


class ExtractionError(PipelineError):
    """Raised when extraction fails for a non-missing-sheet reason."""


class ValidationError(PipelineError):
    """Raised when a record has ERROR-severity validation failures."""


class LoadError(PipelineError):
    """Raised when the DB load transaction fails."""
