from ubinascii import hexlify, unhexlify
from micropython import const
from hexdump import hexdump
from ustruct import unpack_from
import ubluetooth
import gc
import time

_IRQ_SCAN_RESULT = const(5)
_IRQ_SCAN_DONE = const(6)
_IRQ_PERIPHERAL_CONNECT = const(7)
_IRQ_PERIPHERAL_DISCONNECT = const(8)
_IRQ_GATTC_SERVICE_RESULT = const(9)
_IRQ_GATTC_SERVICE_DONE = const(10)
_IRQ_GATTC_CHARACTERISTIC_RESULT = const(11)
_IRQ_GATTC_CHARACTERISTIC_DONE = const(12)
_IRQ_GATTC_DESCRIPTOR_RESULT = const(13)
_IRQ_GATTC_DESCRIPTOR_DONE = const(14)
_IRQ_GATTC_READ_RESULT = const(15)
_IRQ_GATTC_READ_DONE = const(16)
_IRQ_GATTC_WRITE_DONE = const(17)
_IRQ_GATTC_NOTIFY = const(18)
_IRQ_GATTC_INDICATE = const(19)


scan_done = False

ble = ubluetooth.BLE()


class BLECharacteristic:
    def __init__(self, def_handle, value_handle, uuid):
        self.def_handle = def_handle
        self.value_handle = value_handle
        self.uuid = uuid


class BLEDescriptor:
    def __init__(self, handle):
        self.handle = handle
        self.busy = False


STATE_IDLE = const(0)
STATE_CONNECTING = const(1)
STATE_DISCOVERING = const(2)
STATE_READING = const(3)


class BLEDevice:
    def __init__(self, addr_type, addr, adv_type=None, rssi=None, adv_data=None):
        self.addr_type = addr_type
        self.addr = addr
        self.adv_type = adv_type
        self.rssi = rssi
        self.processed = False
        self.service_class_uuids = set()
        self.conn_handle = None
        self.characteristics = {}
        self.descriptors = {}
        self.state = STATE_IDLE
        if adv_data is not None:
            self.parse_advertising_data(adv_data)

    def parse_ad_elem(self, data, idx):
        el_len, ad_type = unpack_from('BB', data, idx)
        idx += 2
        if ad_type == 0x01:
            # Flags
            self.flags = unpack_from('B', data, idx)
            print('flags 0x%02x' % self.flags)
        elif ad_type in (0x02, 0x03):
            # 0x02: Incomplete List of 16-bit Service Class UUIDs
            # 0x03: Complete List of 16-bit Service Class UUIDs
            for i in range(0, el_len, 2):
                uuid = unpack_from('<H', data, idx + i)
                print('service class UUID: 0x%04x' % uuid)
                self.service_class_uuids.add(uuid)
        elif ad_type == 0x16:
            print('service data:')
            hexdump(data[idx:], el_len)
        elif ad_type == 0xff:
            print('manufacturer data:')
            hexdump(data[idx:], el_len)
        elif ad_type == 0x0a:
            # Tx Power Level
            pass
        elif ad_type == 0x1b:
            print('LE Bluetooth Device Address: %s' % hexlify(data[(idx):(idx + el_len)]))
        else:
            print('unknown AD elem 0x%02x' % ad_type)
            hexdump(data[idx:], el_len)
        idx += el_len - 1
        return idx

    def parse_advertising_data(self, data):
        print('%d %s: ' % (self.addr_type, hexlify(self.addr, ':')))
        hexdump(data)
        idx = 0
        while idx < len(data):
            idx = self.parse_ad_elem(data, idx)

    def matches(self, addr_type, addr):
        if self.addr_type != addr_type:
            return False
        if self.addr != addr:
            return False
        return True

    def handle_connection(self, conn_handle):
        print('connected to %s' % self)
        self.conn_handle = conn_handle
        self.state = STATE_IDLE

    def discover_characteristics(self):
        print('discover char start')
        ble.gattc_discover_characteristics(self.conn_handle, 1, 0xffff)
        self.state = STATE_DISCOVERING

    def discover_services(self):
        print('discover srv start')
        ble.gattc_discover_services(self.conn_handle)
        self.state = STATE_DISCOVERING

    def discover_descriptors(self):
        print('discover descriptor start')
        ble.gattc_discover_descriptors(self.conn_handle, 1, 0xffff)
        self.state = STATE_DISCOVERING

    def handle_service_result(self, start_handle, end_handle, uuid):
        print('service: 0x%04x -> 0x%04x %s' % (start_handle, end_handle, uuid))

    def handle_service_discovery_done(self, result):
        self.state = STATE_IDLE

    def handle_char_result(self, def_handle, value_handle, properties, uuid):
        print('char: %x %x %s (%02x)' % (def_handle, value_handle, uuid, properties))
        # if value_handle not in self.characteristics:
        #    self.characteristics[value_handle] = BLECharacteristic(def_handle, value_handle, uuid)

    def handle_char_discovery_done(self, status):
        self.state = STATE_IDLE

    def handle_desc_result(self, desc_handle, uuid):
        print('desc: 0x%02x %s' % (desc_handle, uuid))
        # if desc_handle not in self.descriptors:
        #    self.descriptors[desc_handle] = BLEDescriptor(desc_handle)

    def handle_desc_discovery_done(self, status):
        self.state = STATE_IDLE

    def handle_disconnect(self):
        self.state = STATE_IDLE

    def wait_for_state_change(self, state, timeout=1000):
        start = time.ticks_ms()
        while self.state == state:
            time.sleep_ms(10)
            now = time.ticks_ms()
            if now - start > timeout:
                raise Exception('State change timed out')

    def read_handle(self, handle):
        self.state = STATE_READING
        ble.gattc_read(self.conn_handle, handle)
        self.read_result = None
        self.wait_for_state_change(STATE_READING)
        if self.read_result is None:
            raise Exception('Unable to read handle 0x%04x' % handle)
        res = self.read_result
        self.read_result = None
        return res

    def handle_read_result(self, handle, value):
        self.read_result = bytes(value)

    def handle_read_done(self, handle, status):
        self.state = STATE_IDLE

    def connect(self):
        self.state = STATE_CONNECTING
        ble.gap_connect(self.addr_type, self.addr)

    def is_busy(self):
        return self.state != STATE_IDLE

    def __str__(self):
        return str(hexlify(self.addr, ':'))


_HANDLE_DEVICE_NAME = const(0x03)
_HANDLE_DEVICE_TIME = const(0x41)
_HANDLE_FIRMWARE_AND_BATTERY = const(0x38)


class FlowerCareDevice(BLEDevice):
    def read_name(self):
        return str(self.read_handle(_HANDLE_DEVICE_NAME))

    def read_firmware_version(self):
        response = self.read_handle(_HANDLE_FIRMWARE_AND_BATTERY)
        return ''.join(map(chr, response[2:]))

    def read_battery_level(self):
        response = self.read_handle(_HANDLE_FIRMWARE_AND_BATTERY)
        return unpack_from('B', response, 0)[0]

    def read_time(self):
        return self.read_handle(_HANDLE_DEVICE_TIME)


class BLEDevices:
    def __init__(self):
        self.devices = {}
        self.connections = {}

    def get_by_addr(self, addr_type, addr):
        return self.devices.get((addr_type, addr))

    def get_by_conn(self, conn_handle):
        return self.connections[conn_handle]

    def handle_scan_result(self, addr_type, addr, adv_type, rssi, adv_data):
        print('scan result: %s' % hexlify(addr))
        dev = self.get_by_addr(addr_type, addr)
        if dev is None:
            dev = BLEDevice(addr_type, addr, adv_type, rssi, adv_data)
            self.devices[(addr_type, addr)] = dev
        else:
            dev.parse_advertising_data(adv_data)
            dev.rssi = rssi

    def handle_disconnect(self, conn_handle, addr):
        if conn_handle not in self.connections:
            print('disconnect from %s not registered' % hexlify(addr))
        else:
            dev = self.connections.get(conn_handle)
            if dev is not None:
                dev.handle_disconnect()
            del self.connections[conn_handle]

    def handle_connect(self, addr_type, addr, conn_handle):
        dev = self.get_by_addr(addr_type, addr)
        if dev is None:
            print('connect from unknown device: %s' % hexlify(addr, ':'))
            self.connections[conn_handle] = None
        else:
            dev.handle_connection(conn_handle)
            self.connections[conn_handle] = dev

    def connect(self, dev):
        self.devices[(dev.addr_type, dev.addr)] = dev
        dev.connect()


devices = BLEDevices()


def irq_handler(event, data):
    global scan_done

    if event == _IRQ_SCAN_RESULT:
        # A single scan result.
        addr_type, addr, adv_type, rssi, adv_data = data
        devices.handle_scan_result(addr_type, addr, adv_type, rssi, adv_data)
    elif event == _IRQ_SCAN_DONE:
        # Scan duration finished or manually stopped.
        print('scan done')
        scan_done = True
    elif event == _IRQ_PERIPHERAL_CONNECT:
        # A successful gap_connect().
        conn_handle, addr_type, addr = data
        devices.handle_connect(addr_type, addr, conn_handle)
    elif event == _IRQ_PERIPHERAL_DISCONNECT:
        # Connected peripheral has disconnected.
        conn_handle, addr_type, addr = data
        print('disconnect %d' % conn_handle)
        devices.handle_disconnect(conn_handle, addr)
    elif event == _IRQ_GATTC_SERVICE_RESULT:
        # Called for each service found by gattc_discover_services().
        conn_handle, start_handle, end_handle, uuid = data
        dev = devices.get_by_conn(conn_handle)
        if dev is not None:
            dev.handle_service_result(start_handle, end_handle, uuid)
    elif event == _IRQ_GATTC_SERVICE_DONE:
        # Called once service discovery is complete.
        # Note: Status will be zero on success, implementation-specific value otherwise.
        conn_handle, status = data
        print('service done')
        dev = devices.get_by_conn(conn_handle)
        if dev is not None:
            dev.handle_service_discovery_done(status)
    elif event == _IRQ_GATTC_CHARACTERISTIC_RESULT:
        # Called for each characteristic found by gattc_discover_services().
        conn_handle, def_handle, value_handle, properties, uuid = data
        dev = devices.get_by_conn(conn_handle)
        if dev is not None:
            dev.handle_char_result(def_handle, value_handle, properties, uuid)
    elif event == _IRQ_GATTC_CHARACTERISTIC_DONE:
        # Called once service discovery is complete.
        # Note: Status will be zero on success, implementation-specific value otherwise.
        conn_handle, status = data
        dev = devices.get_by_conn(conn_handle)
        if dev is not None:
            dev.handle_char_discovery_done(status)
    elif event == _IRQ_GATTC_DESCRIPTOR_RESULT:
        # Called for each descriptor found by gattc_discover_descriptors().
        conn_handle, dsc_handle, uuid = data
        dev = devices.get_by_conn(conn_handle)
        if dev is not None:
            dev.handle_desc_result(dsc_handle, uuid)
    elif event == _IRQ_GATTC_DESCRIPTOR_DONE:
        # Called once service discovery is complete.
        # Note: Status will be zero on success, implementation-specific value otherwise.
        conn_handle, status = data
        print('desc done:')
        dev = devices.get_by_conn(conn_handle)
        if dev is not None:
            dev.handle_desc_discovery_done(status)
    elif event == _IRQ_GATTC_READ_RESULT:
        # A gattc_read() has completed.
        conn_handle, value_handle, char_data = data
        dev = devices.get_by_conn(conn_handle)
        if dev is not None:
            dev.handle_read_result(value_handle, char_data)
    elif event == _IRQ_GATTC_READ_DONE:
        # A gattc_read() has completed.
        # Note: The value_handle will be zero on btstack (but present on NimBLE).
        # Note: Status will be zero on success, implementation-specific value otherwise.
        conn_handle, value_handle, status = data
        dev = devices.get_by_conn(conn_handle)
        if dev is not None:
            dev.handle_read_done(value_handle, status)
    elif event == _IRQ_GATTC_WRITE_DONE:
        # A gattc_write() has completed.
        # Note: The value_handle will be zero on btstack (but present on NimBLE).
        # Note: Status will be zero on success, implementation-specific value otherwise.
        conn_handle, value_handle, status = data
        print('write done')
    elif event == _IRQ_GATTC_NOTIFY:
        # A peripheral has sent a notify request.
        conn_handle, value_handle, notify_data = data
        print('notify: %d' % value_handle)
        hexdump(notify_data)
    elif event == _IRQ_GATTC_INDICATE:
        # A peripheral has sent an indicate request.
        conn_handle, value_handle, notify_data = data
        print('indicate:')


ble.irq(irq_handler)
if not ble.active():
    print('Activating')
    ble.active(True)
    print('Activated')

#print('Starting scan')
#ble.gap_scan(20000)

#addr1 = 'C4:7C:8D:6A:35:DE'
addr2 = 'C4:7C:8D:6A:3A:27'

dev = FlowerCareDevice(0, unhexlify(addr2.replace(':', '')))
devices.connect(dev)
dev.wait_for_state_change(STATE_CONNECTING, 5000)
print(dev.read_name())
print(dev.read_battery_level())

"""
dev.discover_services()
while dev.is_busy():
    time.sleep_ms(100)


dev.discover_characteristics()
while dev.is_busy():
    time.sleep_ms(100)


dev.discover_descriptors()
while dev.is_busy():
    time.sleep_ms(100)

for i in range(1, 0x42):
    if i in (0x0a, 0x0b, 0x12, 0x1b, 0x1d, 0x1f, 0x21, 0x2a, 0x3b):
        continue
    dev.read_handle(i)
    while dev.is_busy():
        time.sleep_ms(100)
"""