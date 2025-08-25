"""

wrapper for dealing with launchctl stuff .

"""

import plistlib
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Union, Optional


def get_uid():
	proc = subprocess.run(["/usr/bin/id", "-u"], stdout=subprocess.PIPE)
	proc.check_returncode()
	return int(str(proc.stdout, "ascii"))


UID = get_uid()

LAUNCHD_PATH = Path("/var/db/com.apple.xpc.launchd")
GLOBAL_LAUNCH_AGENTS_PATH = Path("/Library/LaunchAgents")
USER_LAUNCH_AGENTS_PATH = Path("~/Library/LaunchAgents").expanduser()


def find_login_items_plist_path() -> Path:
	# return next(LAUNCHD_PATH.glob("loginitems.*.plist"))
	return LAUNCHD_PATH / f"loginitems.{UID}.plist"


def find_disabled_user_service_targets_path() -> Path:
	# return list(LAUNCHD_PATH.glob("disabled*.plist"))
	return LAUNCHD_PATH / f"disabled.{UID}.plist"


def list_login_items_dict() -> dict[str, str]:
	with open(find_login_items_plist_path(), "rb") as file:
		return plistlib.load(file)


def list_login_items_labels() -> list[str]:
	return list(list_login_items_dict().keys())


def list_disabled_service_targets_labels() -> dict[str, bool]:
	# true indicates disabled, false indicates enabled, i think
	with open(find_disabled_user_service_targets_path(), "rb") as file:
		return plistlib.load(file)


@dataclass
class ServiceTarget:
	label: str

	@property
	def target(self):
		return f"user/{UID}/{self.label}"


def _unwrap(target: Union[ServiceTarget, str]):
	if isinstance(target, ServiceTarget):
		return target.target
	return target


def _launchctl(args: list[str]):
	subprocess.run(["/bin/launchctl", *args]).check_returncode()


def launchctl_enable(service_target: Union[ServiceTarget, str]):
	_launchctl(["enable", _unwrap(service_target)])


def launchctl_disable(service_target: Union[ServiceTarget, str]):
	_launchctl(["disable", _unwrap(service_target)])


@dataclass
class LoginItem(ServiceTarget):
	app_bundle_id: Optional[str]
	disabled: bool


def list_login_items() -> list[LoginItem]:
	disabled_dict = list_disabled_service_targets_labels()
	return [
		LoginItem(
			label=label,
			app_bundle_id=app_bundle_id if "." in app_bundle_id else None,  # weed out the weird numeric ones.
			disabled=disabled_dict.get(label, False)
		) for (label, app_bundle_id) in list_login_items_dict().items()
	]


class ServiceTargetType(Enum):
	GLOBAL = "global"
	USER = "user"


def list_launch_agent_names(type: ServiceTargetType) -> list[str]:
	if type == ServiceTargetType.GLOBAL:
		dir_path = GLOBAL_LAUNCH_AGENTS_PATH
	else:
		dir_path = USER_LAUNCH_AGENTS_PATH

	return [path.name.removesuffix(".plist") for path in dir_path.glob("*.plist")]


@dataclass
class LaunchAgent(ServiceTarget):
	run_at_load: bool
	program: Optional[str]
	program_arguments: Optional[str]
	enabled: bool
	agent_disabled: Optional[bool]  # it can be OVERRIDDEN. this is just what the agent ITSELf reports.


def get_launch_agent(type: ServiceTargetType, label: str):
	if type == ServiceTargetType.GLOBAL:
		dir_path = GLOBAL_LAUNCH_AGENTS_PATH
	else:
		dir_path = USER_LAUNCH_AGENTS_PATH

	path = dir_path / f"{label}.plist"
	with open(path, "rb") as file:
		data = plistlib.load(file)

	disabled_dict = list_disabled_service_targets_labels()
	disabled_by_override_list = disabled_dict.get(label, False)
	disabled_by_task_itself = data.get("Disabled", False)

	enabled = not (disabled_by_override_list or disabled_by_task_itself)

	return LaunchAgent(
		label=label,
		run_at_load=data.get("RunAtLoad", False),
		program=data.get("Program"),
		program_arguments=data.get("ProgramArguments"),
		agent_disabled=data.get("Disabled"),
		enabled=enabled
	)
