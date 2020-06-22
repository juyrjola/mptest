import ustruct
import uctypes
from uctypes import UINT16
from machine import UART


uart = UART(2, 9600)
uart.init(9600, bits=8, parity=None, stop=1, timeout=100)


PM_PACKET = {
    "framelen": (0x00 | UINT16),
    "pm10_standard": (0x02 | UINT16),
    "pm25_standard": (0x04 | UINT16),
    "pm100_standard": (0x06 | UINT16),
    "pm10_env": (0x08 | UINT16),
    "pm25_env": (0x0a | UINT16),
    "pm100_env": (0x0c | UINT16),
    "particles_05um": (0x0e | UINT16),
    "particles_10um": (0x10 | UINT16),
    "particles_25um": (0x12 | UINT16),
    "particles_50um": (0x14 | UINT16),
    "particles_100um": (0x16 | UINT16),
    "unused": (0x18 | UINT16),
    "checksum": (0x1a | UINT16),
}


print('waintig for data')
while True:
    c = uart.read(1)
    if c is None:
        continue
    if c[0] != 0x42:  # 'B'
        print('got data 0x%02x' % c[0])
        continue
    c = uart.read(1)
    if c is None:
        continue
    if c[0] != 0x4d:  # 'M'
        continue
    print('packet found')

    p_fmt = '>HHHHHHHHHHHHHHH'
    p_size = ustruct.calcsize(p_fmt)
    print('reading %d' % p_size)
    buf = uart.read(p_size)
    if len(buf) != p_size:
        print('read invalid number of bytes: %d' % len(buf))
        continue

    p = ustruct.unpack(p_fmt, buf)
    framelen, pm10_standard, pm25_standard, pm100_standard, pm10_env, pm25_env, pm100_env, \
        particles_03um, particles_05um, particles_10um, particles_25um, particles_50um, particles_100um, \
        unused, recv_checksum = p

    calc_checksum = 0x42 + 0x4d
    for b in buf[:-2]:
        calc_checksum = calc_checksum + b

    if calc_checksum != recv_checksum:
        print('checksum mismatch 0x%04x vs 0x%04x' % (calc_checksum, recv_checksum))
        continue

    # print(p.framelen, p.pm10_standard, p.pm25_standard)
