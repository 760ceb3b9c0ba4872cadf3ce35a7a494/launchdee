import io
from pathlib import Path
from typing import Optional, Union

from AppKit import NSBitmapImageRep, NSWorkspace, NSPNGFileType


def get_tiff_icon_from_file(path: Union[Path, str]):
	image = NSWorkspace.sharedWorkspace().iconForFile_(str(path))
	tiff = image.TIFFRepresentation()
	return io.BytesIO(tiff)


def get_app_path_from_bundle_id(bundle_id: str) -> Optional[Path]:
	url = NSWorkspace.sharedWorkspace().URLForApplicationWithBundleIdentifier_(bundle_id)
	if url is None:
		return None
	path = url.path()
	return Path(path)

