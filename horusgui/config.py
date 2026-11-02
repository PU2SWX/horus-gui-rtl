#!/usr/bin/env python
#
#   Horus Telemetry GUI - Configuration
#
#   Mark Jessop <vk5qi@rfhead.net>
#   + RTL-SDR fields + save-safe version handling
#
import json
import logging
import os
from pyqtgraph.Qt import QtCore
from . import __version__
from .modem import populate_modem_settings
from .audio import populate_sample_rates
from horusdemodlib.payloads import download_latest_payload_id_list, download_latest_custom_field_list, read_payload_list, read_custom_field_list
import horusdemodlib.payloads

default_config = {
    "version": __version__,
    "audio_device": "None",
    "audio_sample_rate": "48000",
    "modem": "Horus Binary v1 (Legacy)",
    "baud_rate": -1,
    "habitat_upload_enabled": True,
    "habitat_call": "N0CALL",
    "habitat_lat": 0.0,
    "habitat_lon": 0.0,
    "habitat_alt": 0.0,
    "habitat_antenna": "",
    "habitat_radio": "",
    "horus_udp_enabled": True,
    "horus_udp_port": 55672,
    "ozimux_enabled": False,
    "ozimux_udp_port": 55683,
    "rotator_type": "rotctld",
    "rotator_host": "localhost",
    "rotator_port": 4533,
    "rotator_rangeinhibit": True,
    "logging_enabled": False,
    "log_format": "CSV",
    "log_directory": "",
    "fft_smoothing": False,
    # RTL-SDR
    "rtl_freq": "430.430",
    "rtl_gain": "auto",
    "rtl_ppm": "0",
    "payload_list": json.dumps(horusdemodlib.payloads.HORUS_PAYLOAD_LIST),
    "custom_field_list": json.dumps({})
}

qt_settings = QtCore.QSettings("Project Horus", "Horus-GUI")

def ValueToBool(Value):
    """ Helper function to deal with QSettings inconsistency in handling boolean values """
    if isinstance(Value, bool):
        RetVal = Value
    else:
        RetVal = None
        if isinstance(Value, str):
            if Value.lower() == 'true':
                RetVal = True
            elif Value.lower() == 'false':
                RetVal = False
        else:
            RetVal = bool(Value)
    
    return RetVal


def write_config():
    """ Write global settings into QSettings """
    global default_config, qt_settings

    for _setting in default_config:
        qt_settings.setValue(_setting, default_config[_setting])
    qt_settings.sync()
    
    logging.info("Current configuration saved.")


def read_config(widgets):
    """ Read in configuration settings from Qt """
    global qt_settings, default_config

    OK_VERSIONS = [
        __version__,
        '0.6.1.1', '0.6.1', '0.6.0', '0.5.0-beta1',
        '0.4.2', '0.4.1', '0.4.0',
        '0.3.19', '0.3.18', '0.3.17', '0.3.16', '0.3.15', '0.3.14',
        '0.3.13', '0.3.12', '0.3.11', '0.3.10', '0.3.9', '0.3.8',
        '0.3.7', '0.3.6', '0.3.5', '0.3.4', '0.3.1', '0.2.1',
    ]
    
    stored_keys = set(qt_settings.allKeys())
    stored = qt_settings.value("version")

    if not stored_keys:
        logging.info("No saved configuration found - writing defaults.")
        write_config()
        stored_keys = set(qt_settings.allKeys())

    elif stored is None:
        logging.warning(
            "Saved configuration has no version tag. "
            "Preserving existing values."
        )
        qt_settings.setValue("version", __version__)
        qt_settings.sync()
        stored_keys.add("version")

    elif stored not in OK_VERSIONS:
        logging.warning(
            "Config version %r unknown - keeping saved values, updating version tag.",
            stored,
        )
        qt_settings.setValue("version", __version__)
        qt_settings.sync()

    for _setting in default_config:
        try:
            if _setting in stored_keys:
                _new_setting = qt_settings.value(_setting)
                if _new_setting is not None:
                    default_config[_setting] = _new_setting
            else:
                qt_settings.setValue(_setting, default_config[_setting])
        except Exception as e:
            logging.debug("Missing config setting: %s", e)

    qt_settings.sync()
    if widgets:
        # Habitat Settings
        widgets["sondehubUploadSelector"].setChecked(ValueToBool(default_config["habitat_upload_enabled"]))
        widgets["userCallEntry"].setText(str(default_config["habitat_call"]))
        widgets["userLatEntry"].setText(str(default_config["habitat_lat"]))
        widgets["userLonEntry"].setText(str(default_config["habitat_lon"]))
        widgets["userAltEntry"].setText(str(default_config["habitat_alt"]))
        widgets["userAntennaEntry"].setText(str(default_config["habitat_antenna"]))
        widgets["userRadioEntry"].setText(str(default_config["habitat_radio"]))

        # Horus Settings
        widgets["horusUploadSelector"].setChecked(ValueToBool(default_config["horus_udp_enabled"]))
        widgets["horusUDPEntry"].setText(str(default_config["horus_udp_port"]))
        widgets["ozimuxUploadSelector"].setChecked(ValueToBool(default_config["ozimux_enabled"]))
        widgets["ozimuxUDPEntry"].setText(str(default_config["ozimux_udp_port"]))

        # Try and set the audio device.
        widgets["audioDeviceSelector"].setCurrentText(default_config["audio_device"])
        populate_sample_rates(widgets)
        widgets["audioSampleRateSelector"].setCurrentText(str(default_config["audio_sample_rate"]))

        widgets["horusModemSelector"].setCurrentText(default_config["modem"])
        populate_modem_settings(widgets)

        # Rotator Settings
        widgets["rotatorTypeSelector"].setCurrentText(default_config["rotator_type"])
        widgets["rotatorHostEntry"].setText(str(default_config["rotator_host"]))
        widgets["rotatorPortEntry"].setText(str(default_config["rotator_port"]))
        widgets["rotatorRangeInhibit"].setChecked(ValueToBool(default_config["rotator_rangeinhibit"]))

        # Logging Settings
        widgets["loggingPathEntry"].setText(str(default_config["log_directory"]))
        widgets["loggingFormatSelector"].setCurrentText(default_config["log_format"])
        widgets["enableLoggingSelector"].setChecked(ValueToBool(default_config["logging_enabled"]))

        widgets["fftSmoothingSelector"].setChecked(ValueToBool(default_config["fft_smoothing"]))

        if default_config['baud_rate'] != -1:
            try:
                widgets["horusModemRateSelector"].setCurrentText(str(default_config['baud_rate']))
            except Exception:
                pass

        # RTL-SDR
        if "rtlFreqEntry" in widgets:
            widgets["rtlFreqEntry"].setText(str(default_config.get("rtl_freq", "430.430")))
        if "rtlGainEntry" in widgets:
            widgets["rtlGainEntry"].setText(str(default_config.get("rtl_gain", "auto")))
        if "rtlPpmEntry" in widgets:
            widgets["rtlPpmEntry"].setText(str(default_config.get("rtl_ppm", "0")))


    if 'payload_list' in default_config:
        try:
            _payloads = default_config['payload_list']
            if isinstance(_payloads, str):
                _payloads = json.loads(_payloads)
            _temp = {}
            for _key in _payloads:
                _temp[int(_key)] = _payloads[_key]
            default_config['payload_list'] = _temp
        except Exception as e:
            logging.debug("payload_list parse: %s", e)


def save_config(widgets):
    """ Write out settings to QSettings """
    global default_config

    if widgets:
        try:
            default_config["habitat_upload_enabled"] = widgets[
                "sondehubUploadSelector"
            ].isChecked()
            default_config["version"] = __version__
            default_config["habitat_call"] = widgets["userCallEntry"].text()
            default_config["habitat_lat"] = float(widgets["userLatEntry"].text() or 0)
            default_config["habitat_lon"] = float(widgets["userLonEntry"].text() or 0)
            default_config["habitat_alt"] = float(widgets["userAltEntry"].text() or 0)
            default_config["habitat_antenna"] = widgets["userAntennaEntry"].text()
            default_config["habitat_radio"] = widgets["userRadioEntry"].text()
            default_config["horus_udp_enabled"] = widgets["horusUploadSelector"].isChecked()
            default_config["horus_udp_port"] = int(widgets["horusUDPEntry"].text() or 55672)
            default_config["ozimux_enabled"] = widgets["ozimuxUploadSelector"].isChecked()
            default_config["ozimux_udp_port"] = int(widgets["ozimuxUDPEntry"].text() or 55683)
            default_config["audio_device"] = widgets["audioDeviceSelector"].currentText()
            default_config["audio_sample_rate"] = widgets["audioSampleRateSelector"].currentText()
            default_config["modem"] = widgets["horusModemSelector"].currentText()
            try:
                default_config["baud_rate"] = int(widgets["horusModemRateSelector"].currentText())
            except Exception:
                default_config["baud_rate"] = -1
            default_config["rotator_type"] = widgets["rotatorTypeSelector"].currentText()
            default_config["rotator_host"] = widgets["rotatorHostEntry"].text()
            default_config["rotator_port"] = int(widgets["rotatorPortEntry"].text() or 4533)
            default_config["rotator_rangeinhibit"] = widgets["rotatorRangeInhibit"].isChecked()
            default_config["logging_enabled"] = widgets["enableLoggingSelector"].isChecked()
            default_config["log_directory"] = widgets["loggingPathEntry"].text()
            default_config["log_format"] = widgets["loggingFormatSelector"].currentText()
            default_config["fft_smoothing"] = widgets["fftSmoothingSelector"].isChecked()

            # RTL-SDR
            if "rtlFreqEntry" in widgets:
                default_config["rtl_freq"] = widgets["rtlFreqEntry"].text().strip()
            if "rtlGainEntry" in widgets:
                default_config["rtl_gain"] = widgets["rtlGainEntry"].text().strip()
            if "rtlPpmEntry" in widgets:
                default_config["rtl_ppm"] = widgets["rtlPpmEntry"].text().strip()

            default_config["payload_list"] = json.dumps(horusdemodlib.payloads.HORUS_PAYLOAD_LIST)
            default_config["custom_field_list"] = json.dumps(horusdemodlib.payloads.HORUS_CUSTOM_FIELDS)

            write_config()
        except Exception as e:
            logging.error("save_config failed: %s", e)


def init_payloads(payload_id_list=None, custom_field_list=None):
    """ Attempt to download the latest payload / config data, and update local configs """
    global default_config

    if payload_id_list is None:
        _payload_list = download_latest_payload_id_list(timeout=3)
    else:
        logging.info(f"Using supplied Payload ID list file: {payload_id_list}")
        _payload_list = read_payload_list(payload_id_list)

    if _payload_list:
        if 0 in _payload_list:
            horusdemodlib.payloads.HORUS_PAYLOAD_LIST = _payload_list
            logging.info(f"Updated Payload List Successfuly!")
        else:
            logging.critical("Could not read payload list!")
    else:
        if 'payload_list' in default_config:
            try:
                _payload_list = default_config['payload_list']
                if 0 in _payload_list:
                    horusdemodlib.payloads.HORUS_PAYLOAD_LIST = _payload_list
                    logging.warning(f"Loaded Payload List from local cache, may be out of date!")
                else:
                    logging.critical("Could not read stored payload list!")
            except Exception as e:
                logging.critical(f"Could not read stored payload list - {str(e)}")
        else:
            logging.critical("Payload list not available in local storage!")

    logging.info(f"Payload List contains {len(list(horusdemodlib.payloads.HORUS_PAYLOAD_LIST.keys()))} entries.")

    if custom_field_list is None:
        _custom_fields = download_latest_custom_field_list(timeout=3)
    else:
        logging.info(f"Using supplied Custom Field List file: {custom_field_list}")
        _custom_fields = read_custom_field_list(custom_field_list)

    if _custom_fields:
        if '4FSKTEST-V2' in _custom_fields:
            horusdemodlib.payloads.HORUS_CUSTOM_FIELDS = _custom_fields
            logging.info(f"Updated Custom Field List Successfuly!")
        else:
            logging.critical("Could not read custom field list!")
    else:
        if 'custom_field_list' in default_config:
            try:
                _custom_fields = json.loads(default_config['custom_field_list'])
                if '4FSKTEST-V2' in _custom_fields:
                    horusdemodlib.payloads.HORUS_CUSTOM_FIELDS = _custom_fields
                    logging.warning("Loaded Custom Fields List from local cache, may be out of date!")
                else:
                    logging.critical("Could not read stored custom fields list!")
            except Exception as e:
                logging.critical(f"Could not read stored custom fields list - {str(e)}")
        else:
            logging.critical("Custom Field list not available in local storage!")
    
    logging.info(f"Custom Field list contains {len(list(horusdemodlib.payloads.HORUS_CUSTOM_FIELDS.keys()))} entries.")


if __name__ == "__main__":
    import sys
    logging.basicConfig(
        format="%(asctime)s %(levelname)s: %(message)s", level=logging.DEBUG
    )

    if len(sys.argv) >= 2:
        write_config()

    read_config(None)
