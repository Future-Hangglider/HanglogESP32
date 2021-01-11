import math, time, ustruct
from machine import UART

hposlst = b').38\x0b\x10\x15\x1a\x1f$' # =[41, 46, 51, 56, 11, 16, 21, 26, 31, 36]

class BNO055:
    def __init__(self, luart, letter='Z'):
        self.uart2 = luart
        self.bno055buffer = bytearray(36)
        self.mbno055buffer = memoryview(self.bno055buffer)[12:]
        self.tbno055timeout = 0
        self.bs = bytearray("Zt00000000x0000y0000z0000a0000b0000c0000w0000x0000y0000z0000s00m0000n0000o0000\n")
        self.letter = letter
        self.bs[0] = ord(self.letter)
        self.mbs = memoryview(self.bs)
        self.prevcalibvals = None
        self.prevcalibstat = 0x00

        if not self.bno055write1(0x3D, 0x00):  raise OSError("BAD055_0")   # config_mode
        self.writecalibstat()
        if not self.bno055write1(0x3E, 0x00):  raise OSError("BAD055_1")   # PWR_MODE normal
        if not self.bno055write1(0x3B, 0x00):  raise OSError("BAD055_2")   # UNIT_SEL: C, Degs, m/s^2
        if not self.bno055write1(0x3D, 0x0C):  raise OSError("BAD055_3")   # NDOF mode
        temperatureval = self.bno055read(0x34, 1)
        if temperatureval is None:
            raise OSError("BADTEMP")
        print("Temp%d" % temperatureval[0])

    def bno055write1(self, reg, val):
        self.uart2.write(bytes((0xAA, 0x00, reg, 1, val)))
        time.sleep_ms(20)
        v = self.uart2.read()
        return v == b'\xee\x01'
   
    def bno055read(self, reg, n):
        self.uart2.write(bytes((0xAA, 0x01, reg, n)))
        time.sleep_ms(20)
        r = self.uart2.read()
        if not ((r[0] == 0xBB) and (r[1] == n) and (len(r) == n + 2)):
            return None
        return r[2:]

    def writecalibstat(self):
        cl = None
        try:
            for lcl in open("calibfile%s.txt" % self.letter):
                if len(lcl) == 54:
                    cl = lcl
        except OSError:
            return False   # file missing
        print(cl)
        if cl is None:
            print("bad calib line")
            return False
        calibs = bytearray((0xAA, 0x00, 0x55, 22))
        for i in range(22):
            calibs.append(int(cl[9+i*2:11+i*2], 16))
        prevcalibvals = calibs[4:]
        self.uart2.write(calibs)
        time.sleep_ms(20)
        v = self.uart2.read()
        print(v)
        return v == b'\xee\x01'


    def recordcalibifnecessary(self, calibstat):
        if calibstat == 0xFF and self.prevcalibstat != 0xFF:
            calibs = self.bno055read(0x55, 22)
            if calibs is None:
                return
            if calibs != self.prevcalibvals:
                print("recordingcalibs", calibs)
                fcalib = open("calibfile%s.txt" % self.letter, "a")
                fcalib.write(self.mbs[2:10])
                fcalib.write(" ")
                for c in calibs:
                    fcalib.write("%02X" % c)
                fcalib.write("\n")
                fcalib.flush()
                fcalib.close()
                self.prevcalibvals = calibs
            else:
                pass#("calibvals unchanged")
        self.prevcalibstat = calibstat

    def readhexlifyBNO055(self, timeoutms=20):
        nr = self.uart2.readinto(self.bno055buffer)
        brec = ((self.bno055buffer[0] == 0xBB) and (self.bno055buffer[1] == 34) and (nr == 36))
        print(nr,self.bno055buffer)
        mstamp = time.ticks_ms()
        if brec:
            self.mbs[2:10] = b"%08X" % mstamp
            self.mbs[61:63] = b"%02X" % self.mbno055buffer[23]  # CALIB_STAT in 0x35 
            for i, p in enumerate(hposlst):
                v = self.mbno055buffer[i*2 + 2] + (self.mbno055buffer[i*2 + 3]<<8)
                self.mbs[p:p+4] = b"%04X" % v
            gm = self.bno055buffer[2] + (self.bno055buffer[3]<<8)
            gn = self.bno055buffer[4] + (self.bno055buffer[5]<<8)
            go = self.bno055buffer[6] + (self.bno055buffer[7]<<8)
            self.mbs[64:68] = b"%04X" % gm
            self.mbs[69:73] = b"%04X" % gn
            self.mbs[74:78] = b"%04X" % go
            self.tbno055timeout = 0  # immediately fire off the next request
            self.recordcalibifnecessary(self.mbno055buffer[23])

        if mstamp > self.tbno055timeout:
            self.uart2.write(b"\xAA\x01\x14\x22")
            self.tbno055timeout = mstamp + timeoutms
        return self.bs if brec else None

#qw,qx,qy,qz = ustruct.unpack("<HHHH", bno055buffer[2:10])
#ax,ay,az = ustruct.unpack("<HHH", bno055buffer[10:16])
#gx,gy,gz = ustruct.unpack("<HHH", bno055buffer[16:22])
#"Zt{:08X}x{:04X}y{:04X}z{:04X}".format(mstamp, ax, ay, az)
#"a{:04X}b{:04X}c{:04X}".format(gx, gy, gz)
#"w{:04X}x{:04X}y{:04X}z{:04X}s{:02X}\n".format(qw, qx, qy, qz, calibstat)

    def GetEulerAngles(self):
        # should take from bs-record (but don't forget signs)
        q0,q1,q2,q3 = ustruct.unpack("<hhhh", self.bno055buffer[2:10]) 

        #def ConvertQuatToEuler(q0, q1, q2, q3):
        riqsq = q0*q0 + q1*q1 + q2*q2 + q3*q3 
        iqsq = 1/riqsq 

        r02 = q0*q2*2 * iqsq
        r13 = q1*q3*2 * iqsq
        sinpitch = r13 - r02

        r01 = q0*q1*2 * iqsq
        r23 = q2*q3*2 * iqsq 
        sinroll = r23 + r01 

        r00 = q0*q0*2 * iqsq
        r11 = q1*q1*2 * iqsq
        r03 = q0*q3*2 * iqsq
        r12 = q1*q2*2 * iqsq
        a00=r00 - 1 + r11   
        a01=r12 + r03  
        rads = math.atan2(a00, -a01) 
        northorient = 180 - math.degrees(rads) 
        return math.degrees(math.asin(sinpitch)), math.degrees(math.asin(sinroll)), northorient
