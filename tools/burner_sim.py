#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
    Copyright (C) 2013  Anders Nylund

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 2 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.

Scotte / Bio Comfort pellet burner emulator.

Opens a pty pair and answers the Scotte serial protocol on the master side,
so that Scotteprotocol.Protocol (and the scottecom plugin) can be pointed at
the slave device path instead of /dev/ttyUSB0.  Linux/WSL only.

The simulator is deliberately independent of src/: the frame layouts and the
write-address table below are a stand-in for the hardware, and
tests/test_burner_sim_pty.py cross-checks them against src/Scotteprotocol.
"""

import argparse
import logging
import os
import random
import select
import signal
import sys
import threading
import time

try:
    import termios
    import tty
    HAVE_PTY = hasattr(os, 'openpty')
except ImportError:  # Windows
    termios = None
    tty = None
    HAVE_PTY = False

logger = logging.getLogger('burner_sim')

# frame id -> list of field widths (characters)
FRAME_LAYOUT = {
    'Z00': [5] * 7 + [10, 10] + [5] * 9,
    'Z01': [5] * 46,
    'Z02': [10] * 4,
    'Z03': [5] * 20,
    'Z04': [5] * 2,
    'Z05': [5] * 39,
    'Z06': [5] * 18,
    'Z07': [5] * 40,
    'Z08': [5] * 25,
}

# write address -> (frame, index, decimals, min, max)
WRITE_MAP = {
    'A00': ('Z01', 0, 0, 4, 50),
    'A01': ('Z01', 1, 0, 5, 100),
    'A06': ('Z03', 14, 0, 5, 75),
    'A04': ('Z01', 4, 0, 25, 200),
    'B01': ('Z00', 10, 0, 40, 85),
    'B03': ('Z01', 9, 0, 10, 70),
    'B04': ('Z01', 10, 2, 0.5, 25),
    'B05': ('Z01', 11, 1, 1, 100),
    'B06': ('Z01', 12, 0, 1, 3),
    'C03': ('Z01', 17, 0, 0, 20),
    'C04': ('Z03', 13, 0, 0, 15),
    'D03': ('Z01', 22, 0, 0, 100),
    'E00': ('Z01', 23, 0, 0, 2),
    'E01': ('Z01', 24, 1, 10, 19),
    'E02': ('Z01', 25, 1, 2, 12),
    'E06': ('Z08', 7, 1, 0, 21),
    'E03': ('Z01', 26, 2, 0, 99.99),
    'F00': ('Z01', 27, 0, 400, 2000),
    'F01': ('Z00', 12, 0, 400, 8000),
    'F02': ('Z01', 29, 0, 400, 8000),
    'G00': ('Z00', 13, 0, 0, 10),
    'G01': ('Z01', 31, 0, 50, 90),
    'G02': ('Z01', 32, 1, 1, 20),
    'G03': ('Z01', 33, 2, 0, 5),
    'G04': ('Z01', 34, 1, 1, 50),
    'G05': ('Z01', 39, 0, 50, 150),
    'G06': ('Z01', 40, 0, 50, 150),
    'G07': ('Z01', 41, 0, 1, 120),
    'G08': ('Z01', 42, 0, 0, 60),
    'G09': ('Z04', 0, 0, 0, 3),
    'H04': ('Z03', 10, 0, 0, 1),
    'H07': ('Z01', 44, 0, 0, 1439),
    'I00': ('Z03', 1, 0, 0, 100),
    'I01': ('Z03', 2, 0, 0, 100),
    'I02': ('Z03', 3, 0, 0, 100),
    'I03': ('Z03', 4, 0, 1, 60),
    'I04': ('Z03', 5, 2, 0, 5),
    'I05': ('Z03', 6, 0, 0, 100),
    'I07': ('Z03', 9, 0, 0, 30),
    'B08': ('Z03', 15, 0, 0, 80),
    'B09': ('Z03', 16, 0, 0, 20),
    'K00': ('Z05', 9, 0, 0, 1440),
    'K01': ('Z05', 10, 0, 0, 1440),
    'K02': ('Z05', 11, 0, 0, 1439),
    'K03': ('Z05', 12, 0, 0, 1439),
    'K04': ('Z05', 13, 0, 0, 1439),
    'K05': ('Z05', 14, 0, 0, 1439),
    'K06': ('Z05', 15, 0, 0, 1439),
    'K07': ('Z05', 16, 0, 0, 1439),
    'K08': ('Z05', 17, 0, 0, 1439),
    'F04': ('Z05', 25, 0, 0, 9999),
    'L00': ('Z05', 18, 0, 0, 999),
    'L01': ('Z05', 19, 1, 1, 900),
    'L02': ('Z05', 20, 0, 0, 100),
    'L03': ('Z05', 29, 0, 0, 900),
    'M00': ('Z05', 21, 0, 50, 150),
    'H02': ('Z01', 37, 0, 10, 100),
    'H03': ('Z01', 38, 0, 10, 100),
}

# write-only command addresses (no backing frame index)
COMMANDS = ('V00', 'V01', 'V02', 'D04')

# realistic starting values (raw integers, i.e. already scaled by decimals)
# for writable parameters; anything not listed starts at its minimum
SEED_PARAMS = {
    'A00': 20, 'A01': 60, 'A06': 30, 'A04': 80, 'B01': 60, 'B03': 30,
    'B04': 400, 'B05': 300, 'B06': 2, 'C03': 5, 'C04': 15, 'D03': 50,
    'E00': 1, 'E01': 120, 'E02': 100, 'E06': 90, 'E03': 500,
    'F00': 800, 'F01': 1000, 'F02': 4000, 'G00': 0, 'G01': 70,
    'G02': 60, 'G03': 50, 'G04': 100, 'G05': 100, 'G06': 100,
    'G07': 10, 'G08': 5, 'H02': 10, 'H03': 100, 'L01': 50,
}

MODE_RUNNING = 5
MODE_STOPPED = 9


def xor_checksum(s):
    x = 0
    for c in s:
        x ^= ord(c)
    return x


def add_checksum(s):
    return s + chr(xor_checksum(s))


class BurnerSim(object):
    """Scotte burner emulator on a pty.  Usable as a library or from main()."""

    def __init__(self, seed=None, chip_version=' 6.99', checksum=True,
                 crlf=False, drop_rate=0.0, corrupt_checksum_rate=0.0,
                 delay=0.0, offline_after=None, read_only=False,
                 freeze=False):
        self.rng = random.Random(seed)
        self.chip_version = chip_version
        self.checksum = checksum
        self.crlf = crlf
        self.drop_rate = drop_rate
        self.corrupt_checksum_rate = corrupt_checksum_rate
        self.delay = delay
        self.offline_after = offline_after
        self.read_only = read_only
        self.freeze = freeze

        self.received_commands = []   # exact bytes of every command received
        self.sent_responses = []      # exact bytes of every response sent
        self.command_count = 0
        self.lock = threading.Lock()
        self.table = self._seed_table()
        self._frac = {}               # sub-second remainders for counters
        self._last_tick = time.time()

        self.master_fd = None
        self.slave_fd = None
        self.slave_path = None
        self._thread = None
        self._stop = threading.Event()

    # ------------------------------------------------------------ value table
    def _seed_table(self):
        t = dict((fid, [0] * len(w)) for fid, w in FRAME_LAYOUT.items())
        for addr, (fid, idx, dec, lo, hi) in WRITE_MAP.items():
            if addr in SEED_PARAMS:
                t[fid][idx] = SEED_PARAMS[addr]
            else:
                t[fid][idx] = int(round(lo * 10 ** dec))
        z0 = t['Z00']
        z0[0] = 64          # power %
        z0[1] = 68          # power kW (1 decimal)
        z0[2] = 582         # boiler temp (1 decimal)
        z0[3] = 27          # chute temp
        z0[4] = 105         # smoke temp
        z0[5] = 103         # oxygen % (1 decimal)
        z0[6] = 99          # light
        z0[7] = 15055042    # feeder time
        z0[8] = 0           # ignition time
        z0[9] = 0           # alarm 'ok'
        z0[11] = 100        # oxygen desired (1 decimal)
        z0[16] = MODE_RUNNING
        z0[17] = 2          # model 'Scotte'
        z2 = t['Z02']
        z2[0] = 120000
        z2[1] = 90000
        z2[2] = 4500000
        z2[3] = 3400000
        t['Z03'][8] = 123   # ignition count
        t['Z04'][1] = self.chip_version
        z6 = t['Z06']
        z6[0] = 55
        z6[1] = 48
        z6[2] = 5
        z6[3] = 21
        z6[4] = 12
        return t

    def tick(self, dt):
        """Advance the simulated burner by dt seconds (random walk + counters)."""
        with self.lock:
            z0 = self.table['Z00']
            running = (z0[16] == MODE_RUNNING)

            def walk(v, step, lo, hi):
                v += self.rng.randint(-step, step)
                return max(lo, min(hi, v))

            if running:
                z0[0] = walk(z0[0], 2, 10, 100)
                z0[1] = int(round(z0[0] * 1.06))
                z0[2] = walk(z0[2], 3, 500, 800)
                z0[3] = walk(z0[3], 1, 20, 60)
                z0[4] = walk(z0[4], 2, 80, 180)
                z0[5] = walk(z0[5], 2, 80, 120)
                z0[6] = walk(z0[6], 1, 90, 100)
                self._count(('Z00', 7), dt)
                self._count(('Z02', 0), dt)
                self._count(('Z02', 2), dt)
                self._count(('Z02', 1), dt)
                self._count(('Z02', 3), dt)
            else:
                z0[0] = 0
                z0[1] = 0
                z0[2] = walk(z0[2], 2, 250, 800)
                z0[4] = walk(z0[4], 1, 20, 180)
                z0[5] = 207

    def _count(self, key, dt):
        total = self._frac.get(key, 0.0) + dt
        whole = int(total)
        self._frac[key] = total - whole
        fid, idx = key
        self.table[fid][idx] += whole

    def render_frame(self, frame_id):
        """Return the response string for a poll of frame_id (without CRLF)."""
        with self.lock:
            widths = FRAME_LAYOUT[frame_id]
            vals = self.table[frame_id]
            out = ''
            for w, v in zip(widths, vals):
                out += str(v).rjust(w)[-w:]
        return self._finish(out)

    def _finish(self, payload):
        if self.checksum:
            payload = add_checksum(payload)
        if self.crlf:
            payload += '\r\n'
        return payload

    # -------------------------------------------------------------- dispatch
    def handle_command(self, raw):
        """Process one raw command (bytes); return response bytes or None."""
        self.received_commands.append(raw)
        logger.info('RX %r', raw)
        self.command_count += 1
        if self.offline_after is not None and self.command_count > self.offline_after:
            logger.info('offline: not answering')
            return None
        text = raw.decode('latin-1')
        if self.checksum:
            if xor_checksum(text) != 0:
                return self._reply_text('E0')
            payload = text[:-1]
        else:
            payload = text
        if payload.startswith('Z'):
            if not self.freeze:
                now = time.time()
                self.tick(now - self._last_tick)
                self._last_tick = now
            fid = payload[:3]
            if fid in FRAME_LAYOUT and payload[3:] == '0000':
                return self._reply_raw(self.render_frame(fid))
            return self._reply_text('E1')
        return self._handle_write(payload)

    def _handle_write(self, payload):
        addr, val = payload[:3], payload[3:]
        if self.read_only or not val.isdigit() or len(val) != 4:
            return self._reply_text('E1')
        if addr in COMMANDS:
            with self.lock:
                z0 = self.table['Z00']
                if addr == 'V00':
                    z0[16] = MODE_STOPPED
                elif addr == 'V01':
                    z0[16] = MODE_RUNNING
                elif addr == 'V02':
                    z0[9] = 0
                    if z0[16] >= 8:
                        z0[16] = 0
                elif addr == 'D04':
                    if z0[16] == 13:
                        z0[16] = 0
            return self._reply_text('OK')
        if addr not in WRITE_MAP:
            return self._reply_text('E1')
        fid, idx = WRITE_MAP[addr][0], WRITE_MAP[addr][1]
        with self.lock:
            self.table[fid][idx] = int(val)
        return self._reply_text('OK')

    def _reply_text(self, text):
        if self.crlf and not self.checksum:
            # per Protocol.run: crlf-era chips do not answer writes at all
            return None
        if self.checksum:
            text = add_checksum(text)
        return text.encode('latin-1')

    def _reply_raw(self, text):
        return text.encode('latin-1')

    def _deliver(self, resp):
        """Apply fault injection and write resp to the master fd."""
        if resp is None:
            return
        if self.delay:
            time.sleep(self.delay)
        if self.drop_rate and self.rng.random() < self.drop_rate:
            logger.info('drop: response suppressed')
            return
        if self.corrupt_checksum_rate and self.rng.random() < self.corrupt_checksum_rate:
            body = resp
            tail = b''
            if body.endswith(b'\r\n'):
                body, tail = body[:-2], b'\r\n'
            body = body[:-1] + bytes([body[-1] ^ 0x55])
            resp = body + tail
            logger.info('corrupt: bad checksum byte')
        self.sent_responses.append(resp)
        logger.info('TX %r', resp)
        os.write(self.master_fd, resp)

    # ---------------------------------------------------------------- serving
    def _serve(self):
        buf = b''
        need = 7 + (1 if self.checksum else 0)
        while not self._stop.is_set():
            try:
                r, _, _ = select.select([self.master_fd], [], [], 0.1)
            except (OSError, ValueError):
                break
            if not r:
                continue
            try:
                data = os.read(self.master_fd, 4096)
            except OSError:
                time.sleep(0.05)
                continue
            buf += data
            while True:
                # commands always start with a letter, so stray CR/LF from a
                # crlf-terminated command can be dropped safely
                buf = buf.lstrip(b'\r\n')
                if len(buf) < need:
                    break
                cmd, buf = buf[:need], buf[need:]
                try:
                    self._deliver(self.handle_command(cmd))
                except OSError:
                    return

    def start(self):
        """Open the pty and start serving; return the slave device path."""
        if not HAVE_PTY:
            raise RuntimeError('burner_sim requires a pty (Linux/WSL)')
        self.master_fd, self.slave_fd = os.openpty()
        tty.setraw(self.slave_fd)
        attrs = termios.tcgetattr(self.master_fd)
        attrs[3] &= ~termios.ECHO
        termios.tcsetattr(self.master_fd, termios.TCSANOW, attrs)
        self.slave_path = os.ttyname(self.slave_fd)
        self._stop.clear()
        self._thread = threading.Thread(target=self._serve, name='burner_sim')
        self._thread.daemon = True
        self._thread.start()
        return self.slave_path

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(2.0)
            self._thread = None
        for name in ('master_fd', 'slave_fd'):
            fd = getattr(self, name)
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
                setattr(self, name, None)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description='Scotte pellet burner emulator over a pty (Linux/WSL only)')
    p.add_argument('--seed', type=int, default=None, help='random seed for deterministic drift')
    p.add_argument('--chip-version', default=' 6.99', help='version string reported in Z04 (default " 6.99")')
    p.add_argument('--no-checksum', action='store_true', help='emulate chips without checksums')
    p.add_argument('--crlf', action='store_true', help='terminate responses with CRLF')
    p.add_argument('--drop-rate', type=float, default=0.0, help='fraction of responses silently dropped')
    p.add_argument('--corrupt-checksum-rate', type=float, default=0.0, help='fraction of responses sent with a wrong checksum byte')
    p.add_argument('--delay', type=float, default=0.0, help='seconds to sleep before each response')
    p.add_argument('--offline-after', type=int, default=None, help='stop answering after N commands')
    p.add_argument('--read-only', action='store_true', help='answer E1 to every write')
    p.add_argument('--freeze', action='store_true', help='disable value drift (constant table)')
    p.add_argument('-v', '--verbose', action='store_true', help='log every RX/TX byte sequence')
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                        format='%(asctime)s %(message)s')
    if not HAVE_PTY:
        sys.stderr.write('burner_sim requires Linux/WSL (pty support)\n')
        return 1
    sim = BurnerSim(seed=args.seed, chip_version=args.chip_version,
                    checksum=not args.no_checksum, crlf=args.crlf,
                    drop_rate=args.drop_rate,
                    corrupt_checksum_rate=args.corrupt_checksum_rate,
                    delay=args.delay, offline_after=args.offline_after,
                    read_only=args.read_only, freeze=args.freeze)
    path = sim.start()
    sys.stdout.write('pty: %s\n' % path)
    sys.stdout.flush()
    done = threading.Event()
    signal.signal(signal.SIGINT, lambda s, f: done.set())
    signal.signal(signal.SIGTERM, lambda s, f: done.set())
    while not done.is_set():
        done.wait(0.5)
    sim.stop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
