from backend.services.netcdf_service import NetCDFService


def get_netcdf_service() -> NetCDFService:
    return NetCDFService()
