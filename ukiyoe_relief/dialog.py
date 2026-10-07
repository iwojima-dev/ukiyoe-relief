"""Parameter dialog, generated from core.params.SPEC."""
import os

from qgis.PyQt.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                                 QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel,
                                 QPushButton, QSpinBox, QTabWidget, QVBoxLayout,
                                 QWidget)
from qgis.core import QgsMapLayerProxyModel, QgsSettings
from qgis.gui import QgsFileWidget, QgsMapLayerComboBox, QgsRasterBandComboBox

from .core import params as P

KEY = "ukiyoe_relief/"


class UkiyoeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ukiyo-e Relief")
        self.setMinimumWidth(480)
        self.widgets = {}
        self.labels = {}
        lay = QVBoxLayout(self)

        # --- input / output ------------------------------------------------
        io = QFormLayout()
        self.layer = QgsMapLayerComboBox()
        self.layer.setFilters(QgsMapLayerProxyModel.RasterLayer)
        self.band = QgsRasterBandComboBox()
        self.layer.layerChanged.connect(self.band.setLayer)
        self.band.setLayer(self.layer.currentLayer())
        self.use_canvas = QCheckBox("Limit to current map canvas extent")
        self.output = QgsFileWidget()
        self.output.setStorageMode(QgsFileWidget.SaveFile)
        self.output.setFilter("GeoTIFF (*.tif);;PNG image (*.png)")
        self.also_png = QCheckBox("Also save a PNG copy (plan view)")
        self.add_layer = QCheckBox("Add result to project")
        io.addRow("DEM layer", self.layer)
        io.addRow("Band", self.band)
        io.addRow("", self.use_canvas)
        io.addRow("Output file", self.output)
        io.addRow("", self.also_png)
        io.addRow("", self.add_layer)
        lay.addLayout(io)

        # --- parameter tabs --------------------------------------------------
        tabs = QTabWidget()
        forms = {}
        for t in P.TABS:
            page = QWidget()
            forms[t] = QFormLayout(page)
            tabs.addTab(page, t)
        for name, label, kind, default, lo, hi, dec, tab, tip in P.SPEC:
            if kind == "choice":
                w = QComboBox()
                w.addItems(lo)
            elif kind == "bool":
                w = QCheckBox()
            elif kind == "int":
                w = QSpinBox()
                w.setRange(int(lo), int(hi))
                w.setSingleStep(int(dec or 1))
            else:
                w = QDoubleSpinBox()
                w.setRange(float(lo), float(hi))
                w.setDecimals(int(dec))
                w.setSingleStep(10 ** -int(dec) if dec else 1.0)
            if tip:
                w.setToolTip(tip)
            lab = QLabel(label)
            if tip:
                lab.setToolTip(tip)
            forms[tab].addRow(lab, w)
            self.widgets[name] = (w, kind)
            self.labels[name] = lab
        lay.addWidget(tabs)

        # --- buttons -------------------------------------------------------
        row = QHBoxLayout()
        reset = QPushButton("Reset to defaults")
        reset.clicked.connect(self.reset)
        row.addWidget(reset)
        row.addStretch(1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Print")
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        row.addWidget(bb)
        lay.addLayout(row)

        self.widgets["mode"][0].currentTextChanged.connect(self._mode_changed)
        for w, kind in self.widgets.values():
            if kind == "choice":
                w.currentTextChanged.connect(self._update_enabled)
            elif kind == "bool":
                w.toggled.connect(self._update_enabled)
            else:
                w.valueChanged.connect(self._update_enabled)
        self.load()

    # ----------------------------------------------------------------------
    def _set(self, name, value):
        w, kind = self.widgets[name]
        if kind == "choice":
            i = w.findText(str(value))
            w.setCurrentIndex(max(0, i))
        elif kind == "bool":
            w.setChecked(bool(value))
        else:
            w.setValue(value)

    def _get(self, name):
        w, kind = self.widgets[name]
        if kind == "choice":
            return w.currentText()
        if kind == "bool":
            return w.isChecked()
        return w.value()

    def reset(self):
        for s in P.SPEC:
            self._set(s[0], s[3])

    def load(self):
        self._loading = True
        st = QgsSettings()
        for name, _l, kind, default, *_ in P.SPEC:
            typ = {"bool": bool, "int": int, "float": float}.get(kind, str)
            self._set(name, st.value(KEY + name, default, type=typ))
        self.use_canvas.setChecked(st.value(KEY + "use_canvas", False, type=bool))
        self.also_png.setChecked(st.value(KEY + "also_png", False, type=bool))
        self.add_layer.setChecked(st.value(KEY + "add_layer", True, type=bool))
        self.output.setFilePath(st.value(KEY + "output", "", type=str))
        self._loading = False
        self._mode_changed(self._get("mode"))
        self._update_enabled()

    def save(self):
        st = QgsSettings()
        for s in P.SPEC:
            st.setValue(KEY + s[0], self._get(s[0]))
        st.setValue(KEY + "use_canvas", self.use_canvas.isChecked())
        st.setValue(KEY + "also_png", self.also_png.isChecked())
        st.setValue(KEY + "add_layer", self.add_layer.isChecked())
        st.setValue(KEY + "output", self.output.filePath())

    def _update_enabled(self, *_):
        """Grey out every field that has no effect with the current settings."""
        if getattr(self, "_loading", False):
            return
        for name, rule in P.DEPENDS.items():
            if name not in self.widgets:
                continue
            on = bool(rule(self._get))
            self.widgets[name][0].setEnabled(on)
            self.labels[name].setEnabled(on)

    def _mode_changed(self, mode):
        oblique = mode == "Layered landscape"
        self.also_png.setEnabled(not oblique)

    def _accept(self):
        if self.layer.currentLayer() is None:
            self.setWindowTitle("Ukiyo-e Relief - choose a DEM layer")
            return
        if not self.output.filePath():
            self.setWindowTitle("Ukiyo-e Relief - choose an output file")
            return
        self.save()
        self.accept()

    # ----------------------------------------------------------------------
    def job(self):
        p = P.from_dict({s[0]: self._get(s[0]) for s in P.SPEC})
        lyr = self.layer.currentLayer()
        out = self.output.filePath()
        if not os.path.splitext(out)[1]:
            out += ".png" if p.mode == "Layered landscape" else ".tif"
        return dict(layer=lyr, source=lyr.source(), band=max(1, self.band.currentBand()),
                    params=p, output=out, use_canvas=self.use_canvas.isChecked(),
                    also_png=self.also_png.isChecked(),
                    add_layer=self.add_layer.isChecked())
