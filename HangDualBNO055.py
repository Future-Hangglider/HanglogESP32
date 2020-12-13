from machine import UART, Pin
import time, socket, urandom
from BNO055_class import BNO055
from UDPblackviewphone import connectActivePhone

fconfig = dict(x.strip().split(None, 1)  for x in open("config.txt"))
pinled = Pin(int(fconfig["pinled"]), Pin.OUT)

def MakeBNO055(dev):
    d = dev.split(",")
    u = UART(int(d[0]), baudrate=115200, rx=int(d[1][2:]), tx=int(d[2][2:]))
    for i in range(5):
        try:
            print(u, d[3])
            return BNO055(u, d[3])
        except OSError as e:
            print(e)
        print("fail", i, d)
        time.sleep(0.5)
    
dev1 = MakeBNO055(fconfig["dev1"])
dev2 = MakeBNO055(fconfig["dev2"])

deviceletter = fconfig["deviceletter"]
c = fconfig["connection0"].split(",")
hotspots = { c[0].encode(): (c[1].encode(), c[2], int(c[3])) }
androidipnumber = c[2]
portnumber = int(c[3])
print("deviceletter", deviceletter)

while not connectActivePhone(pinled, hotspots):
    for j in range(3):
        for i in range(7):
            pinled.value(i%2)
            time.sleep_ms(100)
        time.sleep_ms(800)

import socket, urandom
prevflushstamp = 0
nextledonstamp = 0

ubs = bytearray("Ut00000000i00\n")
mubs = memoryview(ubs)

while True:
    try:
        ss = socket.socket()
        ss.settimeout(1)
        print(ss)
        ss.connect(socket.getaddrinfo(androidipnumber, portnumber)[0][-1])
        s = ss.makefile('rwb', 0)
        print(s.readline())
        s.write(b"%c%c%c%c"%(deviceletter,deviceletter,deviceletter,deviceletter))
        dwrite = s.write
        while True:
            tstamp = time.ticks_ms()
            if tstamp > nextledonstamp:
                pv = (0 if pinled.value() else 1)
                pinled.value(pv)
                mubs[2:10] = b"%08X" % tstamp
                mubs[12] = 48+pv #'0'or'1'
                dwrite(ubs)
                nextledonstamp = tstamp + urandom.randint(5000, 10000)//(10 if pv else 1)
            if dev1 is not None:
                b1 = dev1.readhexlifyBNO055(10)
                if b1 is not None:
                    dwrite(b1)
            if dev2 is not None:
                b2 = dev2.readhexlifyBNO055(10)
                if b2 is not None:
                    dwrite(b2)
                
    except OSError as e:
        print("OSError", e)
        time.sleep(2)
