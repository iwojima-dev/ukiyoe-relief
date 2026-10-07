"""QGIS plugin entry: menu/toolbar action, dialog, task launch."""
import os

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
from qgis.core import (QgsApplication, QgsCoordinateTransform, QgsProject)

from .dialog import UkiyoeDialog
from .task import UkiyoeTask

MENU = "&Ukiyo-e Relief"


class UkiyoeReliefPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.toolbar = None
        self.tasks = []

    def initGui(self):
        icon = QIcon(os.path.join(os.path.dirname(__file__), "icon.png"))
        self.action = QAction(icon, "Ukiyo-e Relief...", self.iface.mainWindow())
        self.action.setToolTip("Render a DEM as a Japanese woodblock print")
        self.action.triggered.connect(self.run)
        self.iface.addPluginToRasterMenu(MENU, self.action)
        # own toolbar: the shared Raster toolbar is often hidden, and QGIS
        # restores its visibility from the profile, so the button "vanishes"
        self.toolbar = self.iface.addToolBar("Ukiyo-e Relief")
        self.toolbar.setObjectName("UkiyoeReliefToolbar")
        self.toolbar.addAction(self.action)
        self.toolbar.setVisible(True)

    def unload(self):
        self.iface.removePluginRasterMenu(MENU, self.action)
        if self.toolbar is not None:
            self.toolbar.removeAction(self.action)
            # detach immediately: on reinstall initGui() runs before the
            # deferred delete, and must not meet the old toolbar
            self.toolbar.setObjectName("")
            self.iface.mainWindow().removeToolBar(self.toolbar)
            self.toolbar.deleteLater()
            self.toolbar = None
        self.action = None

    def _canvas_extent(self, layer):
        canvas = self.iface.mapCanvas()
        ext = canvas.extent()
        src = canvas.mapSettings().destinationCrs()
        dst = layer.crs()
        if src != dst:
            tr = QgsCoordinateTransform(src, dst, QgsProject.instance())
            ext = tr.transformBoundingBox(ext)
        return (ext.xMinimum(), ext.yMinimum(), ext.xMaximum(), ext.yMaximum())

    def run(self):
        dlg = UkiyoeDialog(self.iface.mainWindow())
        if not dlg.exec_():
            return
        job = dlg.job()
        if job["use_canvas"]:
            job["extent"] = self._canvas_extent(job["layer"])
        job.pop("layer")
        task = UkiyoeTask(job, self.iface)
        # The task manager deletes the C++ object once the task ends, so the
        # Python wrapper must be dropped via signals, never queried afterwards.
        self.tasks.append(task)
        task.taskCompleted.connect(lambda t=task: self._forget(t))
        task.taskTerminated.connect(lambda t=task: self._forget(t))
        QgsApplication.taskManager().addTask(task)

    def _forget(self, task):
        try:
            self.tasks.remove(task)
        except ValueError:
            pass
