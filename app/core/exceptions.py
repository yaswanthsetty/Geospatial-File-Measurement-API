from fastapi import HTTPException, status


class GeospatialAPIException(HTTPException):
    def __init__(
        self, status_code: int, detail: str, error_code: str = "GEOSPATIAL_ERROR"
    ):
        super().__init__(status_code=status_code, detail=detail)
        self.error_code = error_code


class InvalidFileError(GeospatialAPIException):
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
            error_code="INVALID_FILE",
        )


class UnsupportedGeometryError(GeospatialAPIException):
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail,
            error_code="UNSUPPORTED_GEOMETRY",
        )


class ProcessingError(GeospatialAPIException):
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail,
            error_code="PROCESSING_ERROR",
        )


class ResourceNotFoundError(GeospatialAPIException):
    def __init__(self, detail: str = "Requested resource not found"):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail,
            error_code="RESOURCE_NOT_FOUND",
        )
