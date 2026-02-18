import sys
import os
import time
import shutil
from enum import Enum

# Import sirilpy
from sirilpy.connection import SirilInterface
from sirilpy.exceptions import SirilError, CommandError

# Import PyQt6
try:
    import json
    import subprocess
    from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                                 QHBoxLayout, QTabWidget, QLabel, QLineEdit,
                                 QPushButton, QCheckBox, QComboBox, QGroupBox,
                                 QGridLayout, QTextEdit, QFileDialog, QSpinBox,
                                 QDoubleSpinBox, QScrollArea, QMessageBox,
                                 QTableWidget, QTableWidgetItem, QHeaderView, QFrame) # Added QFrame
    from PyQt6.QtCore import Qt
except ImportError:
    # Fallback to ensure_installed if strictly necessary, but standard environment implies availability
    # For now, just print error if not available (should be handled by environment)
    print("PyQt6 is required. Please install it.")
    sys.exit(1)

# --- Constants for Folder Names ---
DIR_BIASES = "biases"
DIR_FLATS  = "flats"
DIR_DARKS  = "darks"
DIR_LIGHTS = "lights"
DIR_PROCESS = "../process"
DIR_MASTERS = "../masters"

class FilterRowWidget(QWidget):
    def __init__(self, on_delete, parent=None):
        super().__init__(parent)
        self.on_delete = on_delete
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        
        self.cb_type = QComboBox()
        self.cb_type.addItems(["FWHM", "Weighted FWHM", "Roundness", "Background", "Star Count", "Quality"])
        
        self.val_edit = QLineEdit()
        self.val_edit.setPlaceholderText("Value")
        
        self.cb_unit = QComboBox()
        self.cb_unit.addItems(["%", "Sigma"])
        
        self.btn_del = QPushButton("×")
        self.btn_del.setFixedWidth(30)
        self.btn_del.setToolTip("Remove this filter")
        self.btn_del.setStyleSheet("QPushButton { color: #cc0000; font-weight: bold; font-size: 16px; border: 1px solid #ccc; border-radius: 3px; } QPushButton:hover { background-color: #ffebeb; }")
        self.btn_del.clicked.connect(lambda: self.on_delete(self))
        
        layout.addWidget(self.cb_type, 2)
        layout.addWidget(self.val_edit, 2)
        layout.addWidget(self.cb_unit, 1)
        layout.addWidget(self.btn_del, 0)

class PreprocessGUI(QMainWindow):
    def __init__(self, siril_app):
        super().__init__()
        self.siril = siril_app
        self.setWindowTitle("Siril Preprocessing Flow v1.2")
        self.resize(610, 630)
        self.filters = []

        # Style sheet for uniform background
        self.setStyleSheet("""
            QMainWindow, QTabWidget::pane, QScrollArea, QGroupBox, QWidget#tab_content {
                background-color: #f5f5f5;
            }
            QTabWidget::tab-bar {
                left: 5px;
            }
            QTabBar::tab {
                background: #e0e0e0;
                border: 1px solid #ccc;
                padding: 6px 12px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background: #f5f5f5;
                border-bottom-color: #f5f5f5;
            }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit {
                background-color: white;
            }
        """)

        # Main Layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Tabs
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # Create Tabs
        self.create_convert_tab()
        self.create_calibration_tab()
        self.create_registration_tab()
        self.create_stacking_tab()
        self.create_script_tab()

        # Action Buttons
        btn_layout = QHBoxLayout()
        self.btn_generate = QPushButton("Generate Script")
        self.btn_generate.clicked.connect(self.generate_script)
        btn_layout.addWidget(self.btn_generate)

        self.btn_run = QPushButton("Run Script in Siril")
        self.btn_run.clicked.connect(self.run_script)
        # Disable run button if not connected? For now, keep enabled and try connect on click or init
        btn_layout.addWidget(self.btn_run)
        
        # Save Settings Checkbox
        self.chk_save_settings = QCheckBox("Remember Settings")
        self.chk_save_settings.setToolTip("If checked, current settings will be saved and restored on next launch.\nIf unchecked, default settings will be loaded.")
        btn_layout.addWidget(self.chk_save_settings)

        main_layout.addLayout(btn_layout)

        # Initialize UI states
        self.update_ui_states()
        
        # Load settings if available
        self.load_settings()

    def create_convert_tab(self):
        tab = QWidget()
        tab.setObjectName("tab_content")
        layout = QVBoxLayout(tab)
        
        # --- Main Sequence ---
        grp_main = QGroupBox("Main Sequence")
        gl_main = QGridLayout()
        grp_main.setLayout(gl_main)
        
        gl_main.addWidget(QLabel("Basename:"), 0, 0)
        self.conv_basename = QLineEdit("light")
        gl_main.addWidget(self.conv_basename, 0, 1)

        gl_main.addWidget(QLabel("Start Index:"), 0, 2)
        self.conv_start_idx = QLineEdit("1") # Siril default starts usually at 1
        gl_main.addWidget(self.conv_start_idx, 0, 3)

        gl_main.addWidget(QLabel("Output Directory:"), 1, 0)
        self.conv_out_dir = QLineEdit(DIR_PROCESS)
        gl_main.addWidget(self.conv_out_dir, 1, 1)

        self.conv_debayer = QCheckBox("Debayer (Disabled by default)")
        # Generally uncheck by default for convert, usually done at calibration
        self.conv_debayer.setChecked(False) 
        gl_main.addWidget(self.conv_debayer, 1, 2, 1, 2)
        
        layout.addWidget(grp_main)

        # --- Master Creation ---
        grp_masters = QGroupBox("Master Creation")
        v_masters = QVBoxLayout()
        grp_masters.setLayout(v_masters)

        # Bias
        self.create_bias_chk = QCheckBox(f"Create Master Bias (from {DIR_BIASES})")
        self.create_bias_chk.setChecked(True)
        v_masters.addWidget(self.create_bias_chk)

        # Flat
        self.create_flat_chk = QCheckBox(f"Create Master Flat (from {DIR_FLATS})")
        self.create_flat_chk.setChecked(True)
        self.create_flat_chk.toggled.connect(self.update_ui_states)
        v_masters.addWidget(self.create_flat_chk)

        # Flat Options
        self.flat_opts_group = QGroupBox("Flat Calibration Options")
        fl_opts = QGridLayout()
        self.flat_opts_group.setLayout(fl_opts)
        v_masters.addWidget(self.flat_opts_group)

        fl_opts.addWidget(QLabel("Bias Source:"), 0, 0)
        self.flat_bias_source = QComboBox()
        self.flat_bias_source.addItems(["Use Master Bias", "Use Synthetic Bias", "None"])
        self.flat_bias_source.currentIndexChanged.connect(self.update_ui_states)
        fl_opts.addWidget(self.flat_bias_source, 0, 1)

        self.flat_synth_bias_lbl = QLabel("Value:")
        self.flat_synth_bias_val = QLineEdit()
        self.flat_synth_bias_val.setPlaceholderText("e.g. 512 or 64*$OFFSET")
        fl_opts.addWidget(self.flat_synth_bias_lbl, 1, 0)
        fl_opts.addWidget(self.flat_synth_bias_val, 1, 1)

        # Dark
        self.create_dark_chk = QCheckBox(f"Create Master Dark (from {DIR_DARKS})")
        self.create_dark_chk.setChecked(True)
        v_masters.addWidget(self.create_dark_chk)

        layout.addWidget(grp_masters)
        layout.addStretch()
        self.tabs.addTab(tab, "Convert")

    def create_calibration_tab(self):
        tab = QWidget()
        tab.setObjectName("tab_content")
        layout = QVBoxLayout(tab)

        # Sequence Info
        grp_seq = QGroupBox("Sequence")
        gl_seq = QGridLayout()
        grp_seq.setLayout(gl_seq)
        
        gl_seq.addWidget(QLabel("Sequence Name:"), 0, 0)
        self.cal_seq_name = QLineEdit("light")
        gl_seq.addWidget(self.cal_seq_name, 0, 1)
        
        gl_seq.addWidget(QLabel("Output Prefix:"), 0, 2)
        self.cal_prefix = QLineEdit("pp_")
        gl_seq.addWidget(self.cal_prefix, 0, 3)
        layout.addWidget(grp_seq)

        # Masters
        grp_mast = QGroupBox("Masters to Use")
        gl_mast = QGridLayout()
        grp_mast.setLayout(gl_mast)

        # Bias
        self.use_bias_chk = QCheckBox("Use Bias")
        self.use_bias_path = QLineEdit(f"{DIR_MASTERS}/bias_stacked.fit")
        self.use_bias_chk.toggled.connect(lambda c: self.use_bias_path.setEnabled(c))
        self.use_bias_chk.setChecked(False) # Usually off if flats are calibrated
        self.use_bias_path.setEnabled(False)
        gl_mast.addWidget(self.use_bias_chk, 0, 0)
        gl_mast.addWidget(self.use_bias_path, 0, 1)

        # Dark
        self.use_dark_chk = QCheckBox("Use Dark")
        self.use_dark_chk.setChecked(True)
        self.use_dark_path = QLineEdit(f"{DIR_MASTERS}/dark_stacked.fit")
        self.use_dark_chk.toggled.connect(lambda c: self.use_dark_path.setEnabled(c))
        gl_mast.addWidget(self.use_dark_chk, 1, 0)
        gl_mast.addWidget(self.use_dark_path, 1, 1)

        # Dark Opt (Nested under Dark)
        opt_layout = QHBoxLayout()
        opt_layout.setContentsMargins(10, 0, 0, 0) # Small indent within column 1 logic if needed, or just 0
        opt_layout.setSpacing(5)
        opt_layout.addWidget(QLabel("Dark Opt:"))
        self.cal_dark_opt = QComboBox()
        self.cal_dark_opt.addItems(["None", "Auto-evaluation", "Use Exposure"])
        opt_layout.addWidget(self.cal_dark_opt)
        opt_layout.addStretch()
        gl_mast.addLayout(opt_layout, 2, 1)

        # Flat
        self.use_flat_chk = QCheckBox("Use Flat")
        self.use_flat_chk.setChecked(True)
        self.use_flat_path = QLineEdit(f"{DIR_MASTERS}/pp_flat_stacked.fit")
        self.use_flat_chk.toggled.connect(lambda c: self.use_flat_path.setEnabled(c))
        gl_mast.addWidget(self.use_flat_chk, 3, 0)
        gl_mast.addWidget(self.use_flat_path, 3, 1)

        self.cal_fix_xtrans = QCheckBox("Fix X-Trans Artifact")
        self.cal_fix_xtrans.setToolTip("Fix Fujifilm X-Trans AF pixel patterns (requires dark or bias)")
        gl_mast.addWidget(self.cal_fix_xtrans, 4, 0)

        layout.addWidget(grp_mast)

        # Correction & CFA
        grp_corr = QGroupBox("Correction & CFA")
        gl_corr = QGridLayout()
        grp_corr.setLayout(gl_corr)

        gl_corr.addWidget(QLabel("Cosmetic Correction:"), 0, 0)
        self.cal_cc_type = QComboBox()
        self.cal_cc_type.addItems(["None", "Cold/Hot Pixels (from Dark)", "Bad Pixel Map (BPM)"])
        self.cal_cc_type.currentIndexChanged.connect(self.update_ui_states)
        gl_corr.addWidget(self.cal_cc_type, 0, 1, 1, 5) # Spend whole first row

        self.cal_bpm_path_lbl = QLabel("BPM Path:")
        self.cal_bpm_path = QLineEdit(f"{DIR_MASTERS}/bpm.lst")
        gl_corr.addWidget(self.cal_bpm_path_lbl, 1, 0)
        gl_corr.addWidget(self.cal_bpm_path, 1, 1, 1, 5)

        # Hot/Cold Sigma for Dark Optimization
        self.cal_cold_sigma_lbl = QLabel("Cold Sigma:")
        self.cal_cold_sigma = QDoubleSpinBox()
        self.cal_cold_sigma.setValue(3.0)
        self.cal_cold_sigma.setSingleStep(0.1)
        gl_corr.addWidget(self.cal_cold_sigma_lbl, 1, 0)
        gl_corr.addWidget(self.cal_cold_sigma, 1, 1)

        self.cal_hot_sigma_lbl = QLabel("Hot Sigma:")
        self.cal_hot_sigma = QDoubleSpinBox()
        self.cal_hot_sigma.setValue(3.0)
        self.cal_hot_sigma.setSingleStep(0.1)
        gl_corr.addWidget(self.cal_hot_sigma_lbl, 1, 2)
        gl_corr.addWidget(self.cal_hot_sigma, 1, 3)

        self.cal_cfa_chk = QCheckBox("CFA Pattern")
        self.cal_cfa_chk.setChecked(True)
        gl_corr.addWidget(self.cal_cfa_chk, 2, 0)

        self.cal_eq_cfa_chk = QCheckBox("Equalize CFA")
        self.cal_eq_cfa_chk.setChecked(True)
        gl_corr.addWidget(self.cal_eq_cfa_chk, 2, 1)

        self.cal_debayer_chk = QCheckBox("Debayer")
        self.cal_debayer_chk.setToolTip("Uncheck if using Drizzle in Registration")
        self.cal_debayer_chk.setChecked(False) # Often done at registration or here
        self.cal_debayer_chk.toggled.connect(self.update_ui_states)
        gl_corr.addWidget(self.cal_debayer_chk, 2, 2)

        layout.addWidget(grp_corr)
        layout.addStretch()
        self.tabs.addTab(tab, "Calibration")

    def create_registration_tab(self):
        tab = QWidget()
        tab.setObjectName("tab_content")
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        content = QWidget()
        content.setObjectName("tab_content")
        layout = QVBoxLayout(content)
        scroll.setWidget(content)

        # Sequence
        grp_seq = QGroupBox("Sequence")
        gl_seq = QGridLayout()
        grp_seq.setLayout(gl_seq)
        gl_seq.addWidget(QLabel("Sequence Name:"), 0, 0)
        self.reg_seq_name = QLineEdit("pp_light")
        gl_seq.addWidget(self.reg_seq_name, 0, 1)
        gl_seq.addWidget(QLabel("Output Prefix:"), 0, 2)
        self.reg_prefix = QLineEdit("r_")
        gl_seq.addWidget(self.reg_prefix, 0, 3)
        layout.addWidget(grp_seq)

        # Global Options
        grp_global = QGroupBox("Global Registration Options")
        gl_glo = QGridLayout()
        grp_global.setLayout(gl_glo)

        gl_glo.addWidget(QLabel("Transformation:"), 0, 0)
        self.reg_transform = QComboBox()
        self.reg_transform.addItems(["Homography", "Affine", "Similarity", "Euclidean", "Shift"])
        gl_glo.addWidget(self.reg_transform, 0, 1)

        gl_glo.addWidget(QLabel("Layer:"), 0, 2)
        self.reg_layer = QComboBox()
        self.reg_layer.addItems(["Green (Default)", "Red", "Blue"])
        gl_glo.addWidget(self.reg_layer, 0, 3)
        
        self.reg_2pass_chk = QCheckBox("2-Pass Registration")
        self.reg_2pass_chk.toggled.connect(self.update_ui_states)
        gl_glo.addWidget(self.reg_2pass_chk, 1, 0)

        gl_glo.addWidget(QLabel("Min Pairs:"), 1, 2)
        self.reg_minpairs = QSpinBox()
        self.reg_minpairs.setRange(0, 100)
        self.reg_minpairs.setValue(10)
        gl_glo.addWidget(self.reg_minpairs, 1, 3)

        gl_glo.addWidget(QLabel("Max Stars:"), 2, 2)
        self.reg_maxstars = QSpinBox()
        self.reg_maxstars.setRange(0, 20000)
        self.reg_maxstars.setValue(2000)
        gl_glo.addWidget(self.reg_maxstars, 2, 3)

        # Undistortion (Moved here, but still hidden if Drizzle is checked in update_ui_states)
        self.disto_widget = QWidget()
        dist_layout = QHBoxLayout(self.disto_widget)
        dist_layout.setContentsMargins(0, 0, 0, 0)
        self.reg_disto_lbl = QLabel("Undistortion:")
        self.reg_disto = QComboBox()
        self.reg_disto.addItems(["None", "Apply (Image)", "From File", "From Masters"])
        dist_layout.addWidget(self.reg_disto_lbl)
        dist_layout.addWidget(self.reg_disto)
        gl_glo.addWidget(self.disto_widget, 2, 0, 1, 2)

        layout.addWidget(grp_global)

        # Output / Formatting
        grp_fmt = QGroupBox("Output & Registration")
        gl_fmt = QGridLayout()
        grp_fmt.setLayout(gl_fmt)

        self.reg_drizzle_chk = QCheckBox("Drizzle")
        self.reg_drizzle_chk.setToolTip("Requires non-debayered images (Check Calibration settings)")
        self.reg_drizzle_chk.toggled.connect(self.update_ui_states)
        gl_fmt.addWidget(self.reg_drizzle_chk, 0, 0, Qt.AlignmentFlag.AlignTop)

        # Drizzle Options Group (Improved Layout)
        self.drizzle_opts_widget = QWidget()
        dl = QGridLayout(self.drizzle_opts_widget) # Use Grid for better alignment
        dl.setContentsMargins(5, 5, 0, 0)
        
        self.reg_driz_scale_lbl = QLabel("Scale:")
        self.reg_driz_scale = QDoubleSpinBox()
        self.reg_driz_scale.setRange(0.1, 10.0)
        self.reg_driz_scale.setSingleStep(0.1)
        self.reg_driz_scale.setValue(1.0)
        self.reg_driz_scale.setToolTip("Output image scale factor")
        
        self.reg_driz_pixfrac_lbl = QLabel("PixFrac:")
        self.reg_driz_pixfrac = QDoubleSpinBox()
        self.reg_driz_pixfrac.setRange(0.1, 1.0)
        self.reg_driz_pixfrac.setSingleStep(0.1)
        self.reg_driz_pixfrac.setValue(1.0)
        self.reg_driz_pixfrac.setToolTip("Pixel Fraction (Drop size)")
        
        self.reg_driz_kernel_lbl = QLabel("Kernel:")
        self.reg_driz_kernel = QComboBox()
        self.reg_driz_kernel.addItems(["Square", "Point", "Gaussian", "Turbo", "Lanczos2", "Lanczos3"])
        
        dl.addWidget(self.reg_driz_scale_lbl, 1, 0)
        dl.addWidget(self.reg_driz_scale, 1, 1)
        dl.addWidget(self.reg_driz_pixfrac_lbl, 2, 0)
        dl.addWidget(self.reg_driz_pixfrac, 2, 1)
        dl.addWidget(self.reg_driz_kernel_lbl, 3, 0)
        dl.addWidget(self.reg_driz_kernel, 3, 1)
        
        gl_fmt.addWidget(self.drizzle_opts_widget, 1, 0, 1, 6) # Move to row 1, span across

        # Interpolation (Non-Drizzle)
        self.interp_widget = QWidget()
        il = QHBoxLayout(self.interp_widget)
        il.setContentsMargins(0, 0, 0, 0)
        
        self.reg_interp_lbl = QLabel("Interpolation:")
        self.reg_interp = QComboBox()
        self.reg_interp.addItems(["Lanczos4 (Default)", "Cubic", "Linear", "Nearest", "Area", "None"])
        self.reg_interp.setToolTip("Checking Drizzle hides this option")
        
        il.addWidget(self.reg_interp_lbl)
        il.addWidget(self.reg_interp)
        
        gl_fmt.addWidget(self.interp_widget, 1, 0, 1, 2)


        layout.addWidget(grp_fmt)
        
        # Framing (Separate Group, visible only for 2-pass)
        self.grp_framing = QGroupBox("Output Registration")
        gl_framing = QGridLayout()
        self.grp_framing.setLayout(gl_framing)
        
        gl_framing.addWidget(QLabel("Framing:"), 0, 0)
        self.reg_framing = QComboBox()
        self.reg_framing.addItems(["Current (Default)", "Max (Bounding Box)", "Min (Common Area)", "Center of Gravity"])
        self.reg_framing.currentIndexChanged.connect(self.update_ui_states)
        gl_framing.addWidget(self.reg_framing, 0, 1)
        
        layout.addWidget(self.grp_framing)
        layout.addStretch()
        
        # Add scroll to tab layout
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll)
        self.tabs.addTab(tab, "Registration")

    def create_stacking_tab(self):
        tab = QWidget()
        tab.setObjectName("tab_content")
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        content = QWidget()
        content.setObjectName("tab_content")
        layout = QVBoxLayout(content)
        scroll.setWidget(content)

        # Seq & Output
        grp_seq = QGroupBox("Sequence & Output")
        gl_seq = QGridLayout()
        grp_seq.setLayout(gl_seq)
        gl_seq.addWidget(QLabel("Sequence Name:"), 0, 0)
        self.stk_seq_name = QLineEdit("r_pp_light")
        gl_seq.addWidget(self.stk_seq_name, 0, 1)
        gl_seq.addWidget(QLabel("Output File:"), 0, 2)
        self.stk_out_name = QLineEdit("result")
        gl_seq.addWidget(self.stk_out_name, 0, 3)
        layout.addWidget(grp_seq)

        # Method
        grp_meth = QGroupBox("Method & Rejection")
        gl_meth = QGridLayout()
        grp_meth.setLayout(gl_meth)
        
        gl_meth.addWidget(QLabel("Method:"), 0, 0)
        self.stk_method = QComboBox()
        self.stk_method.addItems(["Average with Rejection", "Sum", "Median", "Pixel Maximum", "Pixel Minimum"])
        self.stk_method.currentIndexChanged.connect(self.update_ui_states)
        gl_meth.addWidget(self.stk_method, 0, 1)

        gl_meth.addWidget(QLabel("Rejection Map:"), 0, 2)
        self.stk_rej_map = QComboBox()
        self.stk_rej_map.addItems(["None", "One Map (-rejmap)", "Two Maps (-rejmaps)"])
        gl_meth.addWidget(self.stk_rej_map, 0, 3)

        self.stk_norm_lbl = QLabel("Normalization:")
        self.stk_norm = QComboBox()
        self.stk_norm.addItems(["Additive + Scaling", "None", "Additive", "Multiplicative", "Multiplicative + Scaling"])
        gl_meth.addWidget(self.stk_norm_lbl, 1, 0)
        gl_meth.addWidget(self.stk_norm, 1, 1)

        self.stk_rej_lbl = QLabel("Rejection:")
        self.stk_rej_algo = QComboBox()
        self.stk_rej_algo.addItems(["Sigma Clipping", "Winsorized Sigma Clipping", "MAD Clipping", "Percentile Clipping", "Generalized ESD", "Linear Fit Clipping", "None"])
        gl_meth.addWidget(self.stk_rej_lbl, 2, 0)
        gl_meth.addWidget(self.stk_rej_algo, 2, 1)

        self.stk_sigma_low_lbl = QLabel("Sigma Low:")
        self.stk_sigma_low = QDoubleSpinBox()
        self.stk_sigma_low.setValue(3.0)
        gl_meth.addWidget(self.stk_sigma_low_lbl, 2, 2)
        gl_meth.addWidget(self.stk_sigma_low, 2, 3)

        self.stk_sigma_high_lbl = QLabel("Sigma High:")
        self.stk_sigma_high = QDoubleSpinBox()
        self.stk_sigma_high.setValue(3.0)
        gl_meth.addWidget(self.stk_sigma_high_lbl, 3, 2)
        gl_meth.addWidget(self.stk_sigma_high, 3, 3)

        self.stk_weight_lbl = QLabel("Weighting:")
        self.stk_weight = QComboBox()
        self.stk_weight.addItems(["None", "Noise", "Weighted FWHM", "Number of Stars", "Number of Images"]) # Reordered/named approx
        gl_meth.addWidget(self.stk_weight_lbl, 4, 0)
        gl_meth.addWidget(self.stk_weight, 4, 1)
        
        layout.addWidget(grp_meth)

        # Filters
        self.stk_filters_group = QGroupBox("Image Rejection Filters")
        v_filt = QVBoxLayout()
        self.stk_filters_group.setLayout(v_filt)
        
        self.filter_scroll = QScrollArea()
        self.filter_scroll.setWidgetResizable(True)
        self.filter_scroll.setMinimumHeight(100) # Slightly reduced from 120
        self.filter_scroll.setMaximumHeight(180) # Slightly reduced from 200
        
        self.filter_container = QWidget()
        self.filter_layout = QVBoxLayout(self.filter_container)
        self.filter_layout.setContentsMargins(5, 5, 5, 5)
        self.filter_layout.setSpacing(5)
        self.filter_layout.addStretch()
        
        self.filter_scroll.setWidget(self.filter_container)
        v_filt.addWidget(self.filter_scroll)
        
        btn_add_filt = QPushButton("+ Add Filter")
        btn_add_filt.setStyleSheet("font-weight: bold;")
        btn_add_filt.clicked.connect(self.add_filter_row)
        v_filt.addWidget(btn_add_filt)

        layout.addWidget(self.stk_filters_group)

        # Stacking result
        grp_opts = QGroupBox("Stacking result")
        gl_opts = QGridLayout()
        grp_opts.setLayout(gl_opts)

        self.stk_rgb_eq = QCheckBox("RGB Equalization")
        self.stk_rgb_eq.setChecked(True)
        gl_opts.addWidget(self.stk_rgb_eq, 1, 0)

        self.stk_out_norm = QCheckBox("Output Normalization")
        self.stk_out_norm.setChecked(True)
        gl_opts.addWidget(self.stk_out_norm, 1, 1)

        self.stk_32b = QCheckBox("32-bit Output")
        self.stk_32b.setChecked(True)
        gl_opts.addWidget(self.stk_32b, 1, 2)

        self.stk_bottomup_chk = QCheckBox("Flip Bottom-Up")
        self.stk_bottomup_chk.setToolTip("Apply mirrorx -bottomup after stacking")
        self.stk_bottomup_chk.setChecked(False)
        gl_opts.addWidget(self.stk_bottomup_chk, 1, 3)

        layout.addWidget(grp_opts)

        # Image Stitching (Mosaicing) Options
        self.grp_stitching = QGroupBox("Image Stitching")
        gl_stitch = QGridLayout()
        self.grp_stitching.setLayout(gl_stitch)

        self.stk_maximize = QCheckBox("Maximize Framing")
        self.stk_maximize.setToolTip("Encompass all images (required for overlap norm)")
        self.stk_maximize.toggled.connect(self.update_ui_states)
        gl_stitch.addWidget(self.stk_maximize, 0, 0)

        self.stk_overlap_norm = QCheckBox("Overlap Normalization")
        self.stk_overlap_norm.setToolTip("Compute norm on overlaps (requires Maximize Framing)")
        gl_stitch.addWidget(self.stk_overlap_norm, 0, 1)

        gl_stitch.addWidget(QLabel("Feather:"), 0, 2)
        self.stk_feather = QSpinBox()
        self.stk_feather.setRange(0, 1000)
        self.stk_feather.setSingleStep(10)
        self.stk_feather.setValue(0)
        self.stk_feather.setSuffix(" px")
        gl_stitch.addWidget(self.stk_feather, 0, 3)

        layout.addWidget(self.grp_stitching)
        layout.addStretch()
        
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll)
        self.tabs.addTab(tab, "Stacking")

    def create_script_tab(self):
        tab = QWidget()
        tab.setObjectName("tab_content")
        layout = QVBoxLayout(tab)
        
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setPlaceholderText("Generated script will appear here...")
        self.output_text.setStyleSheet("background-color: white;")
        layout.addWidget(self.output_text)
        
        self.tabs.addTab(tab, "Script")

    def update_ui_states(self):
        # --- Convert Tab ---
        # Flat Bias options
        create_flat = self.create_flat_chk.isChecked()
        self.flat_opts_group.setVisible(create_flat)
        
        if create_flat:
            idx = self.flat_bias_source.currentIndex()
            # 1 = Synthetic
            is_synth = (idx == 1)
            self.flat_synth_bias_val.setVisible(is_synth)
            self.flat_synth_bias_lbl.setVisible(is_synth)

        # --- Calibration Tab ---
        cc_idx = self.cal_cc_type.currentIndex()
        # 1 = Dark, 2 = BPM
        is_dark_cc = (cc_idx == 1)
        is_bpm = (cc_idx == 2)
        
        self.cal_bpm_path.setVisible(is_bpm)
        self.cal_bpm_path_lbl.setVisible(is_bpm)
        
        self.cal_cold_sigma.setVisible(is_dark_cc)
        self.cal_cold_sigma_lbl.setVisible(is_dark_cc)
        self.cal_hot_sigma.setVisible(is_dark_cc)
        self.cal_hot_sigma_lbl.setVisible(is_dark_cc)

        # --- Registration Tab ---
        drizzle = self.reg_drizzle_chk.isChecked()
        pass2 = self.reg_2pass_chk.isChecked()
        
        # Drizzle options visible?
        self.drizzle_opts_widget.setVisible(drizzle)
        
        # Interpolation visible if NOT drizzle
        self.interp_widget.setVisible(not drizzle)
            
        # Framing visible only if 2-pass
        if hasattr(self, 'grp_framing'):
            self.grp_framing.setVisible(pass2)
            if not pass2:
                self.reg_framing.setCurrentIndex(0)

        # Mutual Exclusivity Logic for Drizzle vs Debayer
        # If Drizzle is checked, prevent Debayer in Calibration
        if drizzle:
            self.cal_debayer_chk.setEnabled(False)
            self.cal_debayer_chk.setChecked(False)
            self.cal_debayer_chk.setToolTip("Disabled because Drizzle is enabled (Requires raw Bayer data)")
        else:
            self.cal_debayer_chk.setEnabled(True)
            self.cal_debayer_chk.setToolTip("Uncheck if using Drizzle in Registration")

        # Reverse check: If user checks Debayer, Drizzle should be disabled?
        # But here updates are triggered by toggles. 
        # If I toggle Debayer, I should update Drizzle state.
        debayer = self.cal_debayer_chk.isChecked()
        if debayer:
            self.reg_drizzle_chk.setEnabled(False)
            self.reg_drizzle_chk.setChecked(False)
            self.reg_drizzle_chk.setToolTip("Disabled because Debayer is enabled (Drizzle requires raw Bayer data)")
        else:
            self.reg_drizzle_chk.setEnabled(True)
            self.reg_drizzle_chk.setToolTip("Requires non-debayered images (Check Calibration settings)")

        # --- Stacking Tab ---
        method_idx = self.stk_method.currentIndex() # 0=AvgRej, 1=Sum, 2=Median, 3=Max
        is_rej = (method_idx == 0)
        
        self.stk_rej_algo.setVisible(is_rej)
        self.stk_rej_lbl.setVisible(is_rej)
        self.stk_norm.setVisible(is_rej) # Normalization also usually only for Avg+Rej
        self.stk_norm_lbl.setVisible(is_rej)
        self.stk_sigma_low.setVisible(is_rej)
        self.stk_sigma_low_lbl.setVisible(is_rej)
        self.stk_sigma_high.setVisible(is_rej)
        self.stk_sigma_high_lbl.setVisible(is_rej)
        self.stk_weight.setVisible(is_rej)
        self.stk_weight_lbl.setVisible(is_rej)
        self.stk_filters_group.setVisible(is_rej)

        # Image Stitching visibility depends on Registration Framing == Maximum (Index 1)
        is_max_framing = (self.reg_framing.currentIndex() == 1)
        self.grp_stitching.setVisible(is_max_framing)

        if not is_max_framing:
            self.stk_maximize.setChecked(False)
            self.stk_feather.setValue(0)

        # Overlap Norm requires Maximize Framing
        maximize_checked = self.stk_maximize.isChecked()
        self.stk_overlap_norm.setEnabled(maximize_checked)
        if not maximize_checked:
            self.stk_overlap_norm.setChecked(False)

    def add_filter_row(self):
        row_widget = FilterRowWidget(on_delete=self.remove_filter_row)
        # Insert before the stretch at the end
        self.filter_layout.insertWidget(self.filter_layout.count() - 1, row_widget)
        self.filters.append(row_widget)

    def remove_filter_row(self, row_widget):
        if row_widget in self.filters:
            self.filters.remove(row_widget)
            self.filter_layout.removeWidget(row_widget)
            row_widget.deleteLater()

    def generate_script(self):
        generator = ScriptGenerator(self)
        script = generator.generate()
        self.output_text.setText(script)
        # Switch to Script tab (index 4)
        self.tabs.setCurrentIndex(self.tabs.count() - 1)

    def run_script(self):
        self.generate_script()
        script_content = self.output_text.toPlainText()
        if not script_content.strip():
            return

        lines = script_content.split('\n')
        try:
            for line in lines:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                # Execute command
                self.siril.cmd(line)
            
            QMessageBox.information(self, "Success", "Script execution completed.")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred during execution:\n{str(e)}")


    def closeEvent(self, event):
        self.save_settings()
        event.accept()

    def get_settings_path(self):
        # Determine the directory of the script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(script_dir, "settings.json")

    def save_settings(self):
        settings = {
            "save_enabled": self.chk_save_settings.isChecked()
        }
        
        if self.chk_save_settings.isChecked():
            # Convert Tab
            settings["conv_basename"] = self.conv_basename.text()
            settings["conv_start_idx"] = self.conv_start_idx.text()
            settings["conv_out_dir"] = self.conv_out_dir.text()
            settings["conv_debayer"] = self.conv_debayer.isChecked()
            settings["create_master_bias"] = self.create_bias_chk.isChecked()
            settings["create_master_flat"] = self.create_flat_chk.isChecked()
            settings["flat_bias_source"] = self.flat_bias_source.currentIndex()
            settings["flat_synth_bias_val"] = self.flat_synth_bias_val.text()
            settings["create_master_dark"] = self.create_dark_chk.isChecked()
            
            # Calibration Tab
            settings["cal_seq_name"] = self.cal_seq_name.text()
            settings["cal_prefix"] = self.cal_prefix.text()
            settings["use_bias_chk"] = self.use_bias_chk.isChecked()
            settings["use_bias_path"] = self.use_bias_path.text()
            settings["use_dark_chk"] = self.use_dark_chk.isChecked()
            settings["use_dark_path"] = self.use_dark_path.text()
            settings["use_flat_chk"] = self.use_flat_chk.isChecked()
            settings["use_flat_path"] = self.use_flat_path.text()
            settings["cal_cc_type"] = self.cal_cc_type.currentIndex()
            settings["cal_bpm_path"] = self.cal_bpm_path.text()
            settings["cal_cold_sigma"] = self.cal_cold_sigma.value()
            settings["cal_hot_sigma"] = self.cal_hot_sigma.value()
            settings["cal_cfa_chk"] = self.cal_cfa_chk.isChecked()
            settings["cal_eq_cfa_chk"] = self.cal_eq_cfa_chk.isChecked()
            settings["cal_fix_xtrans"] = self.cal_fix_xtrans.isChecked()
            settings["cal_dark_opt"] = self.cal_dark_opt.currentIndex()
            settings["cal_debayer_chk"] = self.cal_debayer_chk.isChecked()
            
            # Registration Tab
            settings["reg_seq_name"] = self.reg_seq_name.text()
            settings["reg_prefix"] = self.reg_prefix.text()
            settings["reg_transform"] = self.reg_transform.currentIndex()
            settings["reg_layer"] = self.reg_layer.currentIndex()
            settings["reg_2pass_chk"] = self.reg_2pass_chk.isChecked()
            settings["reg_minpairs"] = self.reg_minpairs.value()
            settings["reg_maxstars"] = self.reg_maxstars.value()
            settings["reg_drizzle_chk"] = self.reg_drizzle_chk.isChecked()
            settings["reg_driz_scale"] = self.reg_driz_scale.value()
            settings["reg_driz_pixfrac"] = self.reg_driz_pixfrac.value()
            settings["reg_driz_kernel"] = self.reg_driz_kernel.currentIndex()
            settings["reg_interp"] = self.reg_interp.currentIndex()
            settings["reg_disto"] = self.reg_disto.currentIndex()
            settings["reg_framing"] = self.reg_framing.currentIndex()

            # Stacking Tab
            settings["stk_seq_name"] = self.stk_seq_name.text()
            settings["stk_out_name"] = self.stk_out_name.text()
            settings["stk_method"] = self.stk_method.currentIndex()
            settings["stk_norm"] = self.stk_norm.currentIndex()
            settings["stk_rej_algo"] = self.stk_rej_algo.currentIndex()
            settings["stk_sigma_low"] = self.stk_sigma_low.value()
            settings["stk_sigma_high"] = self.stk_sigma_high.value()
            settings["stk_weight"] = self.stk_weight.currentIndex()
            settings["stk_rgb_eq"] = self.stk_rgb_eq.isChecked()
            settings["stk_out_norm"] = self.stk_out_norm.isChecked()
            settings["stk_32b"] = self.stk_32b.isChecked()
            settings["stk_maximize"] = self.stk_maximize.isChecked()
            settings["stk_overlap_norm"] = self.stk_overlap_norm.isChecked()
            settings["stk_feather"] = self.stk_feather.value()
            settings["stk_rej_map"] = self.stk_rej_map.currentIndex()
            settings["stk_bottomup_chk"] = self.stk_bottomup_chk.isChecked()
            
            # Filters
            filter_data = []
            for filt in self.filters:
                filter_data.append({
                    "type": filt.cb_type.currentIndex(),
                    "value": filt.val_edit.text(),
                    "unit": filt.cb_unit.currentIndex()
                })
            settings["filters"] = filter_data

        try:
            settings_path = self.get_settings_path()
            with open(settings_path, "w") as f:
                json.dump(settings, f, indent=4)
        except Exception as e:
            print(f"Failed to save settings: {e}")

    def load_settings(self):
        settings_path = self.get_settings_path()
        if not os.path.exists(settings_path):
            return
        
        try:
            with open(settings_path, "r") as f:
                settings = json.load(f)
        except Exception:
            return

        if not settings.get("save_enabled", False):
            return

        self.chk_save_settings.setChecked(True)
        
        # Helper to safely set values
        def set_text(widget, key):
            if key in settings: widget.setText(str(settings[key]))
        def set_idx(widget, key):
            if key in settings: widget.setCurrentIndex(int(settings[key]))
        def set_chk(widget, key):
            if key in settings: widget.setChecked(bool(settings[key]))
        def set_float(widget, key):
            if key in settings: widget.setValue(float(settings[key]))
        def set_int(widget, key):
            # Convert to float first to handle cases like 10.0 in json, then int
            if key in settings: widget.setValue(int(float(settings[key])))

        # Convert Tab
        set_text(self.conv_basename, "conv_basename")
        set_text(self.conv_start_idx, "conv_start_idx")
        set_text(self.conv_out_dir, "conv_out_dir")
        set_chk(self.conv_debayer, "conv_debayer")
        
        set_chk(self.create_bias_chk, "create_master_bias")
        set_chk(self.create_flat_chk, "create_master_flat")
        set_idx(self.flat_bias_source, "flat_bias_source")
        set_text(self.flat_synth_bias_val, "flat_synth_bias_val")
        set_chk(self.create_dark_chk, "create_master_dark")

        # Calibration Tab
        set_text(self.cal_seq_name, "cal_seq_name")
        set_text(self.cal_prefix, "cal_prefix")
        set_chk(self.use_bias_chk, "use_bias_chk")
        set_text(self.use_bias_path, "use_bias_path")
        set_chk(self.use_dark_chk, "use_dark_chk")
        set_text(self.use_dark_path, "use_dark_path")
        set_chk(self.use_flat_chk, "use_flat_chk")
        set_text(self.use_flat_path, "use_flat_path")
        
        set_idx(self.cal_cc_type, "cal_cc_type")
        set_text(self.cal_bpm_path, "cal_bpm_path")
        set_float(self.cal_cold_sigma, "cal_cold_sigma")
        set_float(self.cal_hot_sigma, "cal_hot_sigma")
        set_chk(self.cal_cfa_chk, "cal_cfa_chk")
        set_chk(self.cal_eq_cfa_chk, "cal_eq_cfa_chk")
        set_chk(self.cal_debayer_chk, "cal_debayer_chk")
        set_chk(self.cal_fix_xtrans, "cal_fix_xtrans")
        set_idx(self.cal_dark_opt, "cal_dark_opt")

        # Registration Tab
        set_text(self.reg_seq_name, "reg_seq_name")
        set_text(self.reg_prefix, "reg_prefix")
        set_idx(self.reg_transform, "reg_transform")
        set_idx(self.reg_layer, "reg_layer")
        set_chk(self.reg_2pass_chk, "reg_2pass_chk")
        set_int(self.reg_minpairs, "reg_minpairs")
        set_int(self.reg_maxstars, "reg_maxstars")
        set_chk(self.reg_drizzle_chk, "reg_drizzle_chk")
        set_float(self.reg_driz_scale, "reg_driz_scale")
        set_float(self.reg_driz_pixfrac, "reg_driz_pixfrac")
        set_idx(self.reg_driz_kernel, "reg_driz_kernel")
        set_idx(self.reg_interp, "reg_interp")
        set_idx(self.reg_disto, "reg_disto")
        set_idx(self.reg_framing, "reg_framing")

        # Stacking Tab
        set_text(self.stk_seq_name, "stk_seq_name")
        set_text(self.stk_out_name, "stk_out_name")
        set_idx(self.stk_method, "stk_method")
        set_idx(self.stk_norm, "stk_norm")
        set_idx(self.stk_rej_algo, "stk_rej_algo")
        set_float(self.stk_sigma_low, "stk_sigma_low")
        set_float(self.stk_sigma_high, "stk_sigma_high")
        set_idx(self.stk_weight, "stk_weight")
        set_chk(self.stk_rgb_eq, "stk_rgb_eq")
        set_chk(self.stk_out_norm, "stk_out_norm")
        set_chk(self.stk_32b, "stk_32b")
        set_chk(self.stk_maximize, "stk_maximize")
        set_chk(self.stk_overlap_norm, "stk_overlap_norm")
        set_int(self.stk_feather, "stk_feather")
        set_idx(self.stk_rej_map, "stk_rej_map")
        set_chk(self.stk_bottomup_chk, "stk_bottomup_chk")

        # Filters - Clear existing and add saved
        if "filters" in settings:
            # Clear existing filters first
            for f in self.filters[:]:
                self.remove_filter_row(f)

            for f_data in settings["filters"]:
                self.add_filter_row()
                # Check bounds or try/except if index out of range?
                # Assuming saved settings are valid within current combo ranges
                new_filt = self.filters[-1]
                new_filt.cb_type.setCurrentIndex(f_data["type"])
                new_filt.val_edit.setText(f_data["value"])
                new_filt.cb_unit.setCurrentIndex(f_data["unit"])
        
        self.update_ui_states()


class ScriptGenerator:
    def __init__(self, gui: PreprocessGUI):
        self.gui = gui
        
    def generate(self):
        lines = []
        lines.append("# Siril Preprocessing Script")
        lines.append("requires 1.4.0")
        lines.append("")

        # ----------------------------------------------------
        # CONVERT & MASTER CREATION
        # ----------------------------------------------------
        
        # BIAS
        if self.gui.create_bias_chk.isChecked():
            lines.append("# --- Master Bias ---")
            lines.append(f"cd {DIR_BIASES}")
            lines.append(f"convert bias -out={DIR_PROCESS}")
            lines.append(f"cd {DIR_PROCESS}")
            lines.append(f"stack bias rej 3 3 -nonorm -out={DIR_MASTERS}/bias_stacked")
            lines.append("cd ..")
            lines.append("")

        # FLAT
        if self.gui.create_flat_chk.isChecked():
            lines.append("# --- Master Flat ---")
            lines.append(f"cd {DIR_FLATS}")
            lines.append(f"convert flat -out={DIR_PROCESS}")
            lines.append(f"cd {DIR_PROCESS}")
            
            # Calibrate Flat
            flat_seq = "flat"
            bias_src_idx = self.gui.flat_bias_source.currentIndex()
            # 0=Master, 1=Synth, 2=None
            
            if bias_src_idx == 2: # None
                flat_seq = "flat"
            else:
                cmd = "calibrate flat"
                if bias_src_idx == 0: # Master
                    cmd += f" -bias={DIR_MASTERS}/bias_stacked"
                elif bias_src_idx == 1: # Synth
                    val = self.gui.flat_synth_bias_val.text()
                    cmd += f" -bias='={val}'"
                
                lines.append(cmd)
                flat_seq = "pp_flat"

            lines.append(f"stack {flat_seq} rej 3 3 -norm=mul -out={DIR_MASTERS}/pp_flat_stacked")
            lines.append("cd ..")
            lines.append("")

        # DARK
        if self.gui.create_dark_chk.isChecked():
            lines.append("# --- Master Dark ---")
            lines.append(f"cd {DIR_DARKS}")
            lines.append(f"convert dark -out={DIR_PROCESS}")
            lines.append(f"cd {DIR_PROCESS}")
            lines.append(f"stack dark rej 3 3 -nonorm -out={DIR_MASTERS}/dark_stacked")
            lines.append("cd ..")
            lines.append("")

        # LIGHTS CONVERT
        lines.append("# --- Lights Conversion ---")
        lines.append(f"cd {DIR_LIGHTS}")
        conv_base = self.gui.conv_basename.text()
        start = self.gui.conv_start_idx.text()
        out_dir = self.gui.conv_out_dir.text()
        
        # If input files are already .fit, convert might fail if they are not recognized as sequence
        # But convert is designed to build sequence.
        # Issue might be: 'convert light' looks for 'light_*.fit'.
        # If user has 'light_001.fit', it SHOULD work.
        # If it fails, maybe we should try 'convertraw' if they are raw? No, user said .fit.
        
        # Let's ensure strict syntax.
        cmd = f"convert {conv_base}"
        if start: cmd += f" -start={start}"
        if out_dir: cmd += f" -out={out_dir}"
        # cmd += " -fitseq" # REMOVED per user request to ensure .seq file creation
        if self.gui.conv_debayer.isChecked():
            cmd += " -debayer"
        
        lines.append(cmd)
        
        # Ensure we change directory to the output directory (usually ../process)
        # so that subsequent commands (calibrate) can find the sequence.
        if not out_dir: 
            out_dir = DIR_PROCESS
            
        lines.append(f"cd {out_dir}")
        lines.append("")

        # ----------------------------------------------------
        # CALIBRATION
        # ----------------------------------------------------
        lines.append("# --- Calibration ---")
        # Explicit check to ensure we are in the right directory before calibration starts
        # This is redundant if the above `cd` works, but safe.
        # lines.append(f"cd {DIR_PROCESS}") 
        
        cal_seq = self.gui.cal_seq_name.text()
        cmd = f"calibrate {cal_seq}"
        
        if self.gui.use_dark_chk.isChecked():
            cmd += f" -dark={self.gui.use_dark_path.text()}"
        if self.gui.use_flat_chk.isChecked():
            cmd += f" -flat={self.gui.use_flat_path.text()}"
        if self.gui.use_bias_chk.isChecked():
            cmd += f" -bias={self.gui.use_bias_path.text()}"
            
        # Cosmetic
        cc_idx = self.gui.cal_cc_type.currentIndex()
        if cc_idx == 1: # Dark
            cold = self.gui.cal_cold_sigma.value()
            hot = self.gui.cal_hot_sigma.value()
            cmd += f" -cc=dark -coldsigma={cold} -hotsigma={hot}"
        elif cc_idx == 2: # BPM
            cmd += f" -cc=bpm {self.gui.cal_bpm_path.text()}"
            
        # CFA
        if self.gui.cal_cfa_chk.isChecked():
            cmd += " -cfa"
        if self.gui.cal_eq_cfa_chk.isChecked():
            cmd += " -equalize_cfa"
        if self.gui.cal_debayer_chk.isChecked():
            cmd += " -debayer"
            
        prefix = self.gui.cal_prefix.text()
        if prefix:
            cmd += f" -prefix={prefix}"
            
        # Fix X-Trans
        if self.gui.cal_fix_xtrans.isChecked():
            cmd += " -fix_xtrans"
            
        # Dark Optimization
        opt_idx = self.gui.cal_dark_opt.currentIndex()
        if opt_idx == 1: # Auto
            cmd += " -opt"
        elif opt_idx == 2: # Exp
            cmd += " -opt=exp"

        lines.append(cmd)
        lines.append("")

        # ----------------------------------------------------
        # REGISTRATION
        # ----------------------------------------------------
        lines.append("# --- Registration ---")
        reg_seq = self.gui.reg_seq_name.text() # typically pp_light
        prefix = self.gui.reg_prefix.text()
        
        transf_map = {0: "homography", 1: "affine", 2: "similarity", 3: "euclidean", 4: "shift"}
        transf = transf_map.get(self.gui.reg_transform.currentIndex(), "homography")
        
        drizzle = self.gui.reg_drizzle_chk.isChecked()
        pass2 = self.gui.reg_2pass_chk.isChecked()
        
        # layer
        layer_map = {0: "", 1: " -layer=0", 2: " -layer=2"} # 0=Green(default), 1=Red(0), 2=Blue(2) ?? Siril doc says Red=0, Green=1, Blue=2.
        # Siril doc: "-layer= option with an argument ranging from 0 to 2 for red to blue."
        #  Red=0, Green=1, Blue=2.
        # My combo: Green(0), Red(1), Blue(2)
        # So: ComboBox 0 -> Green(1), ComboBox 1 -> Red(0), ComboBox 2 -> Blue(2)
        l_idx = self.gui.reg_layer.currentIndex()
        layer_cmd = ""
        if l_idx == 0: layer_cmd = " -layer=1" # Green
        elif l_idx == 1: layer_cmd = " -layer=0" # Red
        elif l_idx == 2: layer_cmd = " -layer=2" # Blue
        
        # minpairs / maxstars
        minpairs = self.gui.reg_minpairs.value()
        maxstars = self.gui.reg_maxstars.value()
        
        # Framing if 2-pass
        # -framing=current|max|min|cog
        fr_map = {0: "current", 1: "max", 2: "min", 3: "cog"}
        framing = fr_map.get(self.gui.reg_framing.currentIndex(), "current")

        # Interpolation
        # no, ne, cu, la, li, ar
        interp_map = {0: "la", 1: "cu", 2: "li", 3: "ne", 4: "ar", 5: "no"}
        interp = interp_map.get(self.gui.reg_interp.currentIndex(), "la")
        
        # Distortion
        # None, Apply(Image), From File, From Masters
        d_idx = self.gui.reg_disto.currentIndex()
        disto_cmd = ""
        # Only if not drizzle (UI hides it, but logic should also enforce)
        if not drizzle:
             if d_idx == 1: disto_cmd = " -disto=image"
             # File/Master not implemented in simple GUI inputs for simplicity, just logic placeholder

        # Logic
        if pass2:
            lines.append(f"register {reg_seq} -2pass{layer_cmd} -minpairs={minpairs} -maxstars={maxstars}")
            
            # seqapplyreg
            apply_cmd = f"seqapplyreg {reg_seq}"
            if drizzle:
                sc = self.gui.reg_driz_scale.value()
                pf = self.gui.reg_driz_pixfrac.value()
                # kernel: point, turbo, square, gaussian, lanczos2, lanczos3
                k_txt = self.gui.reg_driz_kernel.currentText().lower()
                apply_cmd += f" -drizzle -scale={sc} -pixfrac={pf} -kernel={k_txt}"
                if self.gui.use_flat_chk.isChecked():
                    apply_cmd += f" -flat={self.gui.use_flat_path.text()}"
            else:
                 # Interp
                 apply_cmd += f" -interp={interp}"
                 # Distortion logic mostly applies to 1-pass or seqapplyreg?
                 # Siril docs: seqapplyreg ... -disto=...
                 if disto_cmd: apply_cmd += disto_cmd
            
            apply_cmd += f" -framing={framing}"
            if prefix: apply_cmd += f" -prefix={prefix}"
            lines.append(apply_cmd)

        else:
            # 1-pass register
            # register seqname -transf=...
            cmd = f"register {reg_seq}"
            if transf != "homography":
                cmd += f" -transf={transf}"
            
            cmd += layer_cmd
            cmd += f" -minpairs={minpairs} -maxstars={maxstars}"
            
            if drizzle:
                sc = self.gui.reg_driz_scale.value()
                pf = self.gui.reg_driz_pixfrac.value()
                k_txt = self.gui.reg_driz_kernel.currentText().lower()
                cmd += f" -drizzle -scale={sc} -pixfrac={pf} -kernel={k_txt}"
                if self.gui.use_flat_chk.isChecked():
                    cmd += f" -flat={self.gui.use_flat_path.text()}"
            else:
                if interp != "la": # default lanczos4?
                    cmd += f" -interp={interp}"
                cmd += disto_cmd
            
            if prefix: cmd += f" -prefix={prefix}"
            lines.append(cmd)
            
        lines.append("")

        # ----------------------------------------------------
        lines.append("# --- Stacking ---")
        stk_seq = self.gui.stk_seq_name.text()
        
        meth_idx = self.gui.stk_method.currentIndex()
        # 0=Rej, 1=Sum, 2=Median, 3=Max
        meth_cmd = ""
        if meth_idx == 1: meth_cmd = " sum"
        elif meth_idx == 2: meth_cmd = " median"
        elif meth_idx == 3: meth_cmd = " max"
        else: meth_cmd = " rej" # default
        
        cmd = f"stack {stk_seq}{meth_cmd}"
        
        if meth_idx == 0: # Rejection Only
            # Sigma, Winsorized, MAD, Percentile, GESD, Linear
            # s, w, a, p, g, l
            algo_map = {0: "s", 1: "w", 2: "a", 3: "p", 4: "g", 5: "l", 6: ""}
            algo_char = algo_map.get(self.gui.stk_rej_algo.currentIndex(), "")
            if algo_char:
                sl = self.gui.stk_sigma_low.value()
                sh = self.gui.stk_sigma_high.value()
                cmd += f" {algo_char} {sl} {sh}"

            # Normalization
            # 0=Add+Scale, 1=None, 2=Add, 3=Mul, 4=MulScale
            norm_idx = self.gui.stk_norm.currentIndex()
            if norm_idx == 0:
                cmd += " -norm=addscale"
            elif norm_idx == 1:
                cmd += " -nonorm"
            elif norm_idx == 2:
                cmd += " -norm=add"
            elif norm_idx == 3:
                cmd += " -norm=mul"
            elif norm_idx == 4:
                cmd += " -norm=mulscale"
            
            # Weighting
            # None, Noise, WFWHM, Stars, NbImages
            w_idx = self.gui.stk_weight.currentIndex()
            if w_idx == 1: cmd += " -weight=noise"
            elif w_idx == 2: cmd += " -weight=wfwhm"
            elif w_idx == 3: cmd += " -weight=nbstars"
            elif w_idx == 4: cmd += " -weight=nbstack"
            
            # Filters
            for filt in self.gui.filters:
                t_txt = filt.cb_type.currentText().lower().replace(" ", "")
                # map: fwhm, weightedfwhm->wfwhm, roundness->round, background->bkg, starcount->nbstars, quality->quality
                if "weighted" in t_txt: t_txt = "wfwhm"
                elif "round" in t_txt: t_txt = "round"
                elif "background" in t_txt: t_txt = "bkg"
                elif "star" in t_txt: t_txt = "nbstars"
                
                val_txt = filt.val_edit.text().strip()
                if not val_txt:
                    continue
                    
                u_txt = filt.cb_unit.currentText()
                if u_txt == "Sigma": u_txt = "k"
                elif u_txt == "Value": u_txt = ""
                # % stays %
                
                cmd += f" -filter-{t_txt}={val_txt}{u_txt}"


        if self.gui.stk_rgb_eq.isChecked(): cmd += " -rgb_equal"
        if self.gui.stk_out_norm.isChecked(): cmd += " -output_norm"
        if self.gui.stk_32b.isChecked(): cmd += " -32b"
        
        out_file = self.gui.stk_out_name.text()
        if out_file: cmd += f" -out={out_file}"
        
        # New options
        if self.gui.stk_maximize.isChecked():
            cmd += " -maximize"
            if self.gui.stk_overlap_norm.isChecked():
                cmd += " -overlap_norm"
        
        feather_val = self.gui.stk_feather.value()
        if feather_val > 0:
            cmd += f" -feather={feather_val}"
            
        rej_map_idx = self.gui.stk_rej_map.currentIndex()
        if rej_map_idx == 1:
            cmd += " -rejmap"
        elif rej_map_idx == 2:
            cmd += " -rejmaps"

        lines.append(cmd)
        lines.append("")
        
        lines.append("# --- Post-Processing ---")
        lines.append(f"load {out_file}")
        
        if self.gui.stk_bottomup_chk.isChecked():
            lines.append("mirrorx -bottomup")
            
        # save ../output_filename_$LIVETIME:%d$s
        lines.append(f"save ../{out_file}_$LIVETIME:%d$s")
        lines.append("cd ..") # Quote not strictly needed for ..
        lines.append("close")
        
        return "\n".join(lines)


# --- Main Entry Point ---

def run_app():
    # Detect Siril connection
    app = QApplication(sys.argv)
    
    # Try connecting to Siril
    siril_iface = SirilInterface()
    try:
        siril_iface.connect()
    except Exception as e:
        print(f"Could not connect to Siril: {e}")
        # We can still run the GUI for testing script generation even without connection
        # But for 'Run' button we need it.
    
    gui = PreprocessGUI(siril_iface)
    gui.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    run_app()
