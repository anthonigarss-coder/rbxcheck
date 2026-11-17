"""rbxcheck : valide des modèles 3D avant l'import dans Roblox Studio."""

from .checks import PROFILES, Config, check_file
from .models import Issue, Mesh, Report, Severity

__version__ = "0.1.0"
__all__ = ["PROFILES", "Config", "Issue", "Mesh", "Report", "Severity", "check_file", "__version__"]
