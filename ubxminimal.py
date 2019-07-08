import ustruct, time, machine, os

if os.uname()[0] == "esp8266":
    import micropython
    micropython.kbd_intr(-1)  # disable keyboard interrupts as otherwise gets killed by Ctrl-Cs
    uartUBX = machine.UART(0, baudrate=9600)
else:
    # The RX2 and TX2 on side of ESP32
    uartUBX = machine.UART(1, baudrate=9600, rx=16, tx=17)

def sendNMEA(comm):
    s = 0
    for c in comm:
        s ^= c
    uartUBX.write(b"${:s}*{:02x}\r\n".format(comm, s))

def appendchecksumUBX(comm):
    ca, cb = 0, 0
    for c in comm[2:]:
        ca = (ca + c) & 0xFF
        cb = (cb + ca) & 0xFF
    comm.append(ca)
    comm.append(cb)

def sendUBX(clsID, msgID, payload):  # look up on p138
    comm = bytearray((0xb5, 0x62, clsID, msgID, len(payload) & 0xFF, (len(payload)>>8) & 0xFF))
    comm.extend(payload)
    appendchecksumUBX(comm)
    uartUBX.write(comm)

def setbaud(baudrate):
    sendNMEA(b"PUBX,41,1,0007,0003,%d,0" % baudrate)
    uartUBX.init(baudrate=baudrate)

    
def msgoutputs(msgIDmap, measRate):
    for msgId, cycles in msgIDmap.items():
        sendNMEA(b"PUBX,40,{:s},0,{:d},0,0,0,0".format(msgId, cycles))
    if measRate:
        sendUBX(0x06, 0x08, ustruct.pack("<HHH", measRate, 1, 0))  # UBX-CFG-RATE

def rflush():
    for i in range(10):
        uartUBX.read()
        time.sleep_ms(200)
        
def initUBX():
    setbaud(115200)
    rflush()
    
    for msgId in ["GLL", "GSV", "GSA", "GGA", "VTG", "RMC", "ZDA"]:
        sendNMEA(b"PUBX,40,{:s},0,{:d},0,0,0,0".format(msgId, 0))

    sendUBX(0x06, 0x08, ustruct.pack("<HHH", 200, 1, 0))  # UBX-CFG-RATE
    rflush()
    
    # Request record stream of type (b0, b1) at rate b2
    sendUBX(0x06, 0x01, b"\x02\x15\x01")  # UBX-RXM-RAWX
    sendUBX(0x06, 0x01, b"\x02\x13\x01")  # UBX-RXM-SFRBX
    sendUBX(0x06, 0x01, b"\x01\x22\x01")  # UBX-NAV-CLOCK
    sendUBX(0x06, 0x01, b"\x01\x30\x01")  # UBX-NAV-SVINFO

    rflush()

#Baidu
#B5 62 06 4A 18 00 00 00 00 00 00 00 00 00 1F 00 00 00 FF FF FF FF 00 00 00 00 00 00 00 00 83 AC