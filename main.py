from __future__ import annotations

import traceback
from pathlib import Path
from typing import Any

import wx
import wx.dataview

from file_icon import get_tiff_icon_from_file, get_app_path_from_bundle_id
from launchd_lib import list_login_items, launchctl_disable, launchctl_enable, LoginItem, list_launch_agent_names, \
	ServiceTargetType, get_launch_agent, LaunchAgent


class BaseRowsWindow(wx.Window):
	def __init__(self, parent, frame: MyFrame):
		super().__init__(parent=parent)

		self.frame = frame

		sizer = wx.BoxSizer(wx.VERTICAL)
		self.dataview = wx.dataview.DataViewListCtrl(self)
		sizer.Add(self.dataview, flag=wx.EXPAND | wx.ALL, proportion=1, border=4)
		self.setup_dataview()

		self.SetSizer(sizer)

		self.update()
		self.dataview.Bind(wx.dataview.EVT_DATAVIEW_ITEM_VALUE_CHANGED, self.on_item_value_changed)

	def update(self):
		self.dataview.DeleteAllItems()
		for row in self.get_rows():
			self.dataview.AppendItem(row)
		self.dataview.Update()

	def on_item_value_changed(self, event: wx.dataview.DataViewEvent):
		try:
			col = event.GetColumn()
			row = self.dataview.ItemToRow(event.GetItem())
			# this is not the LITERAL row (because the column can be sortable) but instead the row in the data.
			value = self.dataview.GetValue(row, col)
			self.on_event(col, row, value)
		except ValueError:
			traceback.print_exc()
			exception = traceback.format_exc(chain=False, limit=0).strip()

			dialog = wx.MessageDialog(
				parent=self,
				caption="Error while toggling service",
				message=exception,
				style=wx.ICON_ERROR | wx.OK
			)
			dialog.ShowWindowModal()
			self.update()

	def setup_dataview(self):
		raise NotImplementedError

	def get_rows(self):
		raise NotImplementedError

	def on_event(self, col: int, row: int, value: Any):
		raise NotImplementedError


class LoginItemsWindow(BaseRowsWindow):
	login_items: list[LoginItem]

	def setup_dataview(self):
		self.dataview.AppendToggleColumn(
			label="Enabled",
			align=wx.ALIGN_CENTER,
			width=wx.COL_WIDTH_AUTOSIZE,
			flags=wx.dataview.DATAVIEW_COL_SORTABLE
		)
		self.dataview.AppendIconTextColumn(
			label="Label",
			align=wx.ALIGN_LEFT,
			flags=wx.dataview.DATAVIEW_COL_SORTABLE | wx.dataview.DATAVIEW_COL_RESIZABLE
		)
		self.dataview.SetRowHeight(24)

	def get_rows(self):
		self.login_items = list_login_items()
		for login_item in self.login_items:
			if login_item.app_bundle_id:
				app_path = get_app_path_from_bundle_id(login_item.app_bundle_id)
			else:
				app_path = None

			if app_path:
				icon_bundle = wx.IconBundle()
				icon_bundle.AddIcon(
					stream=get_tiff_icon_from_file(app_path),
					type=wx.BITMAP_TYPE_TIFF
				)
				bitmap_bundle = wx.BitmapBundle.FromIconBundle(icon_bundle)
			else:
				bitmap_bundle = wx.BitmapBundle()

			yield [
				not login_item.disabled,
				wx.dataview.DataViewIconText(
					text=login_item.label,
					bitmap=bitmap_bundle
				)
			]

	def on_event(self, col: int, row: int, value: Any):
		if col == 0:
			# enabled toggle
			item = self.login_items[row]
			if value:
				launchctl_enable(item)
			else:
				launchctl_disable(item)


class LaunchAgentsWindow(BaseRowsWindow):
	launch_agents: list[LaunchAgent]

	def setup_dataview(self):
		self.dataview.AppendToggleColumn(
			label="Enabled",
			align=wx.ALIGN_CENTER,
			width=wx.COL_WIDTH_AUTOSIZE,
			flags=wx.dataview.DATAVIEW_COL_SORTABLE | wx.dataview.DATAVIEW_COL_REORDERABLE
		)
		self.dataview.AppendToggleColumn(
			label="Run at login",
			mode=wx.dataview.DATAVIEW_CELL_INERT,
			align=wx.ALIGN_CENTER,
			width=wx.COL_WIDTH_AUTOSIZE,
			flags=wx.dataview.DATAVIEW_COL_SORTABLE | wx.dataview.DATAVIEW_COL_REORDERABLE
		)
		self.dataview.AppendTextColumn(
			label="Type",
			align=wx.ALIGN_LEFT,
			width=wx.COL_WIDTH_AUTOSIZE,
			flags=wx.dataview.DATAVIEW_COL_SORTABLE | wx.dataview.DATAVIEW_COL_REORDERABLE
		)
		self.dataview.AppendIconTextColumn(
			label="Label",
			align=wx.ALIGN_LEFT,
			flags=wx.dataview.DATAVIEW_COL_SORTABLE | wx.dataview.DATAVIEW_COL_REORDERABLE | wx.dataview.DATAVIEW_COL_RESIZABLE
		)
		self.dataview.SetRowHeight(24)

	def get_rows(self):
		self.launch_agents = []

		for launch_agent_type in [ServiceTargetType.USER, ServiceTargetType.GLOBAL]:
			launch_agent_names = list_launch_agent_names(launch_agent_type)

			type_name = (
				"User" if launch_agent_type == ServiceTargetType.USER else
				"Global" if launch_agent_type == ServiceTargetType.GLOBAL else
				"???"
			)

			for name in launch_agent_names:
				try:
					launch_agent = get_launch_agent(launch_agent_type, name)
				except ValueError:
					traceback.print_exc()
					print(f"Skipping LaunchAgent {name}, got exception while parsing!")
					continue

				if launch_agent.program:
					target_path = Path(launch_agent.program)
				elif launch_agent.program_arguments and len(launch_agent.program_arguments):
					target_path = Path(launch_agent.program_arguments[0]).resolve()
				else:
					target_path = None

				if target_path:
					if not target_path.exists():
						print(f"Skipping grabbing icon for LaunchAgent {name} because target path does not exist")
						target_path = None

				final_path = None
				if target_path:
					# try to see if path is in a .app
					app_path = None
					for ancestor in target_path.parents:
						if ancestor.is_dir() and ancestor.name.endswith(".app"):
							app_path = ancestor
							break

					final_path = app_path or target_path

				if final_path:
					icon_bundle = wx.IconBundle()
					icon_bundle.AddIcon(
						stream=get_tiff_icon_from_file(final_path),
						type=wx.BITMAP_TYPE_TIFF
					)
					bitmap_bundle = wx.BitmapBundle.FromIconBundle(icon_bundle)
				else:
					bitmap_bundle = wx.BitmapBundle()

				self.launch_agents.append(launch_agent)

				yield [
					launch_agent.enabled,
					launch_agent.run_at_load,
					type_name,
					wx.dataview.DataViewIconText(
						text=name,
						bitmap=bitmap_bundle
					)
				]

	def on_event(self, col: int, row: int, value: Any):
		if col == 0:
			# enabled toggle
			item = self.launch_agents[row]
			if value:
				launchctl_enable(item)
			else:
				launchctl_disable(item)


class MyFrame(wx.Frame):
	def __init__(self):
		super().__init__(
			parent=None,
			title="launchdee",
			size=wx.Size(512, 544)
		)

		self.SetMinSize(wx.Size(320, 320))

		sizer = wx.BoxSizer(wx.VERTICAL)
		notebook = wx.Notebook(self)

		notebook.AddPage(
			page=LaunchAgentsWindow(notebook, frame=self),
			text="Launch agents"
		)
		notebook.AddPage(
			page=LoginItemsWindow(notebook, frame=self),
			text="Login items"
		)

		sizer.Add(notebook, flag=wx.EXPAND | wx.ALL, proportion=1, border=12)
		self.SetSizer(sizer)

		"""
		self.statusbar = wx.StatusBar(parent=self)
		self.statusbar.SetStatusText("launchdee")

		sizer = wx.BoxSizer(wx.HORIZONTAL)
		self.statusbar.SetSizer(sizer)
		sizer.AddStretchSpacer()

		self.progress = wx.ActivityIndicator(parent=self.statusbar)
		self.progress.Hide()
		sizer.Add(self.progress, flag=wx.ALIGN_CENTER_VERTICAL)
		sizer.AddSpacer(8)

		self.SetStatusBar(self.statusbar)
		"""

	def start_progress(self):
		pass
		# self.progress.Start()
		# self.progress.Show()
		# self.statusbar.Layout()
		# self.statusbar.Refresh()

	def stop_progress(self):
		pass
		# self.progress.Hide()
		# self.progress.Stop()


def main():
	app = wx.App()
	frame = MyFrame()
	frame.Show()
	app.MainLoop()


if __name__ == '__main__':
	main()
