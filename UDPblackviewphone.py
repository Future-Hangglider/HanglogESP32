import network, socket, time, machine

sockudp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sockudp.settimeout(0.02)
si = network.WLAN(network.STA_IF) 

# Connect to Blackview/S5 (Android) phone
def connectActivePhone(pled):
    hotspots = { }
    for l in open("hotspots.txt", "rb"):
        s = l.split()
        hotspots[s[0]] = (s[1], s[2].decode(), int(s[3]))
    print(hotspots)
    
    si.active(True)
    siscanned = si.scan()
    siscanned.sort(key=lambda X:X[3])
    while siscanned:
        wc = siscanned.pop()
        print(wc)
        wconn = wc[0]
        if wconn in hotspots:
            wpass, host, port = hotspots[wconn]
            break
            
    else:
        return None, None
    si.connect(wconn, wpass)
    while not si.isconnected():
        time.sleep_ms(100)
        pled.value(1-pled.value())
    return host, port

# udpaddr = ("192.168.43.1", 9019)  # ip default for android
secondaddr = None
def dwrite(mess, udpaddr):
    try:
        sockudp.sendto(mess, udpaddr)
    except OSError as e:
        print("dwrite", e)

