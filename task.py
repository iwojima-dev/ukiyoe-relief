"""Background rendering task."""
import os
import traceback

from qgis.core import Qgis, QgsMessageLog, QgsProject, QgsRasterLayer, QgsTask

from .core import pipeline


class _Cancelled(Exception):
    pass


class UkiyoeTask(QgsTask):
    def __init__(self, job, iface):
        super().__init__("Ukiyo-e Relief: printing", QgsTask.CanCancel)
        self.job = job
        self.iface = iface
        self.written = []
        self.error = None

    def _progress(self, pct, msg=""):
        if self.isCanceled():
            raise _Cancelled()
        self.setProgress(float(pct))
        if msg:
            self.setDescription("Ukiyo-e Relief: " + msg)

    def run(self):
        j = self.job
        try:
            self.written = pipeline.run_file(
                j["source"], j["output"], j["params"], band=j["band"],
                extent=j.get("extent"), also_png=j["also_png"],
                progress=self._progress)
            return True
        except _Cancelled:
            return False
        except Exception:  # noqa: BLE001 - report everything to the log
            self.error = traceback.format_exc()
            return False

    def finished(self, ok):
        bar = self.iface.messageBar()
        if not ok:
            if self.error:
                QgsMessageLog.logMessage(self.error, "Ukiyo-e Relief", Qgis.Critical)
                bar.pushMessage("Ukiyo-e Relief", "Rendering failed - see the log panel.",
                                level=Qgis.Critical, duration=10)
            else:
                bar.pushMessage("Ukiyo-e Relief", "Cancelled.", level=Qgis.Info, duration=4)
            return
        for path in self.written:
            if path.lower().endswith(".tif") and self.job["add_layer"]:
                name = os.path.splitext(os.path.basename(path))[0]
                lyr = QgsRasterLayer(path, name)
                if lyr.isValid():
                    QgsProject.instance().addMapLayer(lyr)
        bar.pushMessage("Ukiyo-e Relief", "Saved: " + "; ".join(self.written),
                        level=Qgis.Success, duration=8)
