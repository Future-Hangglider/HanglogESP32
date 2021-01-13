import uasyncio as asyncio
import uasyncio.stream
from asyncutils import fconfig, wificonnect, initUBX, mountsd, \
                       streamUBX, encodeUBX, pinled, flashseq, batteryvoltage
import socket, os, time

deviceletter = fconfig["deviceletter"]

fdatebasedname = None
sddir = None
sdfileout = None
nbytesout = 0

androidipnumber, portnumber = None, None
socketstream = None
socketstreamcmd = None

battvoltmsg = None
async def ledflashingtask():
    global battvoltmsg
    lnbytesout = 0
    n = 0
    while True:
        battvolt = batteryvoltage()
        if battvolt != 0 and (n%5) == 0:
            battvoltmsg = encodeUBX(0x21, 0x04, ("battvolt=%4.2fv" % battvolt).encode())  # UBX-LOG-STRING

        battfac = max(0.1, battvolt - 6)/4
        battms = int(battfac*800)
        if sdfileout is None and socketstream is None:
            if fdatebasedname is None:
                await flashseq((1400, 500, 400, 500, 200, battms))
            else:
                await flashseq((500, 50, 60, 50, 200, battms))
        
        elif nbytesout - lnbytesout > 40:
            lnbytesout = nbytesout
            if sdfileout is not None:
                await flashseq((1500, 100, 200, 100, 200, 100, 200, 100, 200, battms))
            elif socketstream is not None:
                await flashseq((1500, 100, 200, battms))
                await flashseq((1500, 100, 200, battms))
            else:
                await flashseq((1500, battms, 1500, battms))
            
        else:
            await flashseq((400, 1000, 200, battms))
        n += 1


        
socketreadlinestack = [ ]
async def socketstreamcmdtask():
    global socketstreamcmd, socketstream, battvoltmsg, sddir
    while len(socketreadlinestack) == 0 or socketreadlinestack[0] != "-SDMODE":
        if fdatebasedname is None and battvoltmsg is not None and socketstream is not None:
            try:
                await socketstream.awrite(battvoltmsg)
            except OSError as e:
                print("OSError writing battvoltmsg")
            battvoltmsg = None 
        await asyncio.sleep_ms(100)
        
    if sddir is None:
        sddir = mountsd()
    socketstreamcmd, socketstream = socketstream, None

    while True:
        try:
            if len(socketreadlinestack) == 3:
                rld, rl = socketreadlinestack.pop(), socketreadlinestack.pop()
                if rl == "-DRL":
                    print("listing", rld)
                    await socketstreamcmd.awrite(("List '%s'\n" % rld).encode())
                    for l in os.listdir(rld):
                        nbytes = os.stat("%s/%s"%(rld,l))[6]
                        await socketstreamcmd.awrite(("%s %d\n" % (l, nbytes)).encode())
                    await socketstreamcmd.awrite((".\n").encode())
                elif rl == "-DRR":
                    print("reading", rld)
                    print(os.stat(rld))
                    nbytes = os.stat(rld)[6]
                    await socketstreamcmd.awrite(("%d\n" % nbytes).encode())
                    fin = open(rld, "rb")
                    while True:
                        d = fin.read(500)
                        if not d:
                            break
                        await socketstreamcmd.awrite(d)
                        if len(socketreadlinestack) >= 2 and socketreadlinestack[1] == "-SDMODE":
                            break
                elif rl == "-DRE":
                    print("erasing", rld)
                    try:
                        os.remove(rld)
                        msg = "Removed '%s'\n"%rld
                    except OSError:
                        msg = "Failed\n"
                    await socketstreamcmd.awrite(msg.encode())
            await asyncio.sleep_ms(100)
        except OSError as e:
            print("socketstream3 OSError", e)
            socketstream = None
            await asyncio.sleep_ms(2000)
        
async def manageconnectiontask():
    global socketstream, sdfileout, socketstreamcmd, sddir
    global androidipnumber, portnumber
    # this won't return with None unless there is an SDCard option
    androidipnumber, portnumber = await wificonnect()  
    
    if androidipnumber is not None:
        while True:
            try:
                if socketstream is None:
                    ss = socket.socket()
                    ss.settimeout(1)
                    print("new socket connection", ss)
                    ss.connect(socket.getaddrinfo(androidipnumber, portnumber)[0][-1])
                    lsocketstream = uasyncio.stream.Stream(ss)
                    print(await lsocketstream.readline())
                    t0 = None
                    await lsocketstream.awrite(b"%c%c%c%c"%(deviceletter,deviceletter,deviceletter,deviceletter))
                    if socketstreamcmd is None:
                        socketstream = lsocketstream
                    else:
                        socketstreamcmd = lsocketstream  # drop back into cmd stream on reconnect
                        
                t0 = None
                while (socketstream is not None) or (socketstreamcmd is not None):
                    print("await socketstream.readline")
                    rl = (await (socketstream or socketstreamcmd).readline()).decode().strip()
                    print("socketstream line", [rl])
                    while len(socketreadlinestack) > 2:
                        socketreadlinestack.pop(0)
                    socketreadlinestack.append(rl)
                    
            except OSError as e:
                print("socketstream2 OSError", e)
                socketstream = None  # cmdstream stays not none as a placeholder
                await asyncio.sleep_ms(2000)
                if t0 is None:
                    t0 = time.time()
                elif "wifi2sdtimeout" in fconfig and time.time() - t0 > int(fconfig["wifi2sdtimeout"]):
                    print("Quitting out of socket stream to SD card on delay ", time.time() - t0)
                    break

                
                
    # no wifi found, and timeout set, drop into SD card plotting 
    else:
        while fdatebasedname is None:
            print("waiting for fdatebasedname")
            await asyncio.sleep_ms(1000)
        sddir = mountsd()
        if sddir is not None:
            sdfilename = "%s/%s%s.ubx" % (sddir, fdatebasedname, deviceletter)
            print("Opening sdfile", sdfilename)
            sdfileout = open(sdfilename, "wb")
        else:
            loop.create_task(manageconnectiontask())
        
async def streamgpstask():
    global fdatebasedname, socketstream, nbytesout, battvoltmsg
    fdatebasedname = await initUBX()
    while True:
        fdata = await streamUBX.read(-1)
        if socketstream is not None:
            try:
                if battvoltmsg is not None and fdata[:4] == b'\xb5\x62\x01\x30':
                    print(battvoltmsg)
                    await socketstream.awrite(battvoltmsg)
                await socketstream.awrite(fdata)
            except OSError as e:
                print("socketstream1 OSError", e)
                socketstream = None  # will kick off connecting again
                
        if sdfileout is not None:
            try:
                if battvoltmsg is not None and fdata[:4] == b'\xb5\x62\x01\x30':
                    sdfileout.write(battvoltmsg)
                sdfileout.write(fdata)
                sdfileout.flush()
            except OSError as e:
                print("SDFile OSError", e)

        if battvoltmsg is not None and fdata[:4] == b'\xb5\x62\x01\x30':
            battvoltmsg = None

        if sdfileout is not None or socketstream is not None:
            np, nbytesout = nbytesout, nbytesout+len(fdata)
            if np//100000 != nbytesout//100000:
                print("bytes:", nbytesout)

loop = asyncio.get_event_loop()
loop.create_task(manageconnectiontask())
loop.create_task(streamgpstask())
loop.create_task(ledflashingtask())
loop.create_task(socketstreamcmdtask())
loop.run_forever()

    