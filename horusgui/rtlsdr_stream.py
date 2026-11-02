# RTL-SDR (RTL2832U) input for Horus GUI
#
# Reads IQ from the dongle, performs a USB demodulation entirely in-process,
# and hands 48 kHz / int16 / mono audio to the FFT + modem, exactly like
# AudioStream (audio.py) and UDPStream do. Nothing downstream changes.
import logging
import queue
import threading
import time
import numpy as np
from scipy.signal import firwin, fftconvolve

RTLSDR_DEVICE_NAME = "RTL-SDR (RTL2832U)"

SDR_FS = 960000  # RTL-SDR sample rate. 960k is outside the unusable 300-900 kHz range.
AUDIO_FS = 48000  # Audio rate expected by the modem.
DECIM = SDR_FS // AUDIO_FS  # 20
IQ_OFFSET = SDR_FS // 4  # Hardware is tuned 240 kHz above the dial frequency, to keep the DC spike out of the way.
READ_SIZE = 512 * DECIM  # 10240 IQ samples per read (multiple of 512, of DECIM and of 4)
AGC_TARGET = 3000.0  # Target audio RMS (int16 counts), approx -20 dBFS.

# Audio passband of the USB filter (Hz). Horus GUI estimator range is 100 - 4000 Hz.
USB_LOW = 100.0
USB_HIGH = 5000.0


class USBDownconverter(object):
    """ Complex IQ at SDR_FS (dial frequency at -IQ_OFFSET) -> real USB audio at AUDIO_FS. """

    def __init__(self):
        # Stage 1: lowpass + decimate to 48 kHz complex.
        self.h1 = firwin(127, 12000.0, fs=SDR_FS).astype(np.float32)
        self.hist1 = np.zeros(len(self.h1) - 1, dtype=np.complex64)

        # Stage 2: complex bandpass keeping only positive frequencies (USB), so that
        # signals below the dial frequency (LSB side) are rejected instead of mirrored.
        _centre = (USB_LOW + USB_HIGH) / 2.0
        _half = (USB_HIGH - USB_LOW) / 2.0
        _lp = firwin(255, _half, fs=AUDIO_FS)
        _n = np.arange(len(_lp))
        self.h2 = (_lp * np.exp(2j * np.pi * _centre * _n / AUDIO_FS)).astype(np.complex64)
        self.hist2 = np.zeros(len(self.h2) - 1, dtype=np.complex64)

        # Mixer: multiplying by j^n shifts -fs/4 up to 0 Hz.
        self.mix = np.array([1, 1j, -1, -1j], dtype=np.complex64)
        self.mix_block = np.tile(self.mix, READ_SIZE // 4)

        self.level = None  # AGC level, initialised from the first block

    def process(self, iq):
        """ Process one block of READ_SIZE complex samples. Returns int16 audio (READ_SIZE/DECIM samples). """
        x = iq.astype(np.complex64) * self.mix_block

        x = np.concatenate((self.hist1, x))
        self.hist1 = x[-(len(self.h1) - 1):]
        y = fftconvolve(x, self.h1, mode="valid")[::DECIM].astype(np.complex64)

        y = np.concatenate((self.hist2, y))
        self.hist2 = y[-(len(self.h2) - 1):]
        a = fftconvolve(y, self.h2, mode="valid").real

        # Simple AGC: fast attack, slow release.
        _rms = float(np.sqrt(np.mean(a * a))) + 1e-12
        if self.level is None:
            self.level = _rms
        else:
            _alpha = 0.3 if _rms > self.level else 0.02
            self.level = (1 - _alpha) * self.level + _alpha * _rms
        a = a * (AGC_TARGET / self.level)

        return np.clip(a, -32768, 32767).astype(np.int16)


class RTLSDRStream(object):
    """ Same interface as AudioStream: start_stream(info_callback) in a worker thread, stop() to halt.

    The dongle is read asynchronously by a dedicated thread, which only queues the raw IQ.
    Processing happens in this (worker) thread, so a slow GUI/modem can never make us stop
    polling the USB device (which would silently drop samples and break packets).
    """

    def __init__(self, frequency_hz, gain="auto", ppm=0, block_size=8192, fft_input=None, modem=None, stats_callback=None):
        self.frequency_hz = frequency_hz
        self.gain = gain
        self.ppm = ppm
        self.block_size = block_size
        self.fft_input = fft_input
        self.modem = modem
        self.stats_callback = stats_callback

        self.running = True
        self.stopped = threading.Event()
        self.sdr = None
        self.dropped = 0

    def _reader(self, sdr, callback):
        """ Runs the (blocking) async read loop until cancel_read_async() is called. """
        try:
            sdr.read_samples_async(callback, READ_SIZE)
        except Exception as e:
            if self.running:
                logging.exception("RTL-SDR - Read error.", exc_info=e)

    def start_stream(self, info_callback=None):
        if info_callback:
            self.stats_callback = info_callback

        sdr = None
        reader = None
        try:
            from rtlsdr import RtlSdr

            sdr = RtlSdr()
            self.sdr = sdr
            sdr.sample_rate = SDR_FS
            sdr.center_freq = self.frequency_hz + IQ_OFFSET
            if self.ppm != 0:
                sdr.freq_correction = self.ppm
            sdr.gain = self.gain
            logging.info(f"RTL-SDR - Started. Dial {self.frequency_hz/1e6:.4f} MHz USB, gain {self.gain}, {self.ppm} ppm.")

            iq_queue = queue.Queue(maxsize=200)  # roughly 2 seconds of IQ

            def _on_samples(samples, context=None):
                try:
                    iq_queue.put_nowait(np.array(samples, dtype=np.complex64))
                except queue.Full:
                    self.dropped += 1

            reader = threading.Thread(target=self._reader, args=(sdr, _on_samples), daemon=True)
            reader.start()

            demod = USBDownconverter()
            iq_pending = np.zeros(0, dtype=np.complex64)
            pending = np.zeros(0, dtype=np.int16)
            last_report = time.time()

            while self.running:
                try:
                    chunk = iq_queue.get(timeout=0.5)
                except queue.Empty:
                    if not reader.is_alive():
                        if self.running:
                            logging.error("RTL-SDR - Reader stopped unexpectedly.")
                        break
                    continue

                iq_pending = np.concatenate((iq_pending, chunk))
                while len(iq_pending) >= READ_SIZE:
                    pending = np.concatenate((pending, demod.process(iq_pending[:READ_SIZE])))
                    iq_pending = iq_pending[READ_SIZE:]

                while len(pending) >= self.block_size:
                    self.handle_samples(pending[: self.block_size].tobytes())
                    pending = pending[self.block_size:]

                if self.dropped and (time.time() - last_report) > 5:
                    logging.warning(f"RTL-SDR - Processing is too slow, dropped {self.dropped} blocks of IQ.")
                    self.dropped = 0
                    last_report = time.time()

        except Exception as e:
            logging.exception("RTL-SDR - Error, stopping.", exc_info=e)
        finally:
            if sdr is not None:
                try:
                    sdr.cancel_read_async()
                except Exception:
                    pass
                if reader is not None:
                    reader.join(timeout=2)
                try:
                    sdr.close()
                except Exception:
                    pass
            self.stopped.set()
            logging.debug("Stopped RTL-SDR stream thread")

    def handle_samples(self, data):
        """ Same flow as AudioStream.handle_samples """
        if self.fft_input:
            self.fft_input(data)

        if self.modem:
            _stats = self.modem.add_samples(data)
            if _stats:
                if self.stats_callback:
                    self.stats_callback.emit(_stats)

    def stop(self):
        """ Halt stream, and wait (briefly) for the dongle to be released. """
        self.running = False
        try:
            if self.sdr is not None:
                self.sdr.cancel_read_async()
        except Exception:
            pass
        self.stopped.wait(timeout=3)
