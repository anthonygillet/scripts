import sys, os, time, struct, Queue, threading

if sys.platform == 'win32':
  from twisted.internet import win32eventreactor
  win32eventreactor.install()
  import pywintypes

from twisted.internet import protocol, reactor, defer
from twisted.internet.protocol import Protocol
from twisted.internet.serialport import SerialPort
from twisted.protocols import basic
from twisted.internet.defer import AlreadyCalledError

sys.stdout = open('/var/log/insteonserver.log', 'w', 0)

class L:
    PLM             = "11 CB DB"
    ACK             = "06"
    NAK             = "15"
    PREFIX          = "02"
    INSTEON         = "62"
    X10             = "63"
    FLAGS           = "0F"
    THERM_FLAGS     = "0F"
    EXT_FLAGS       = "1F"
    CMD_ON          = "11"
    CMD_OFF         = "13"
    CMD_STATUS      = "19"
    CMD_SLOW_ON     = "2E"
    CMD_SLOW_OFF    = "2F"
    CMD_ALL_LINK    = "30"
    CMD_X10ADDRESS  = "00"
    CMD_X10COMMAND  = "80"
    CMD_T_ZONE_INFO = "6A"
    CMD_TZ_SETPOINT = "20"
    CMD_TZ_TEMP     = "00"
    CMD_T_CONTROL   = "6B"
    CMD_TC_GETMODE  = "02"
    CMD_TC_AMBIENT  = "03"
    CMD_TC_HEAT     = "04"
    CMD_TC_COOL     = "05"
    CMD_TC_AUTO     = "06"
    CMD_TC_FANON    = "07"
    CMD_TC_FANOFF   = "08"
    CMD_TC_ALLOFF   = "09"
    CMD_TC_PROGHEAT = "0A"
    CMD_TC_PROGCOOL = "0B"
    CMD_TC_PROGAUTO = "0C"
    CMD_TC_STATUS   = "0D"
    CMD_TC_SETMODE  = "0F"
    CMD_T_SETCOOL   = "6C"
    CMD_T_SETHEAT   = "6D"
    X10_A1          = "66"
    X10_A2          = "6E"
    X10_A3          = "62"
    X10_A4          = "6A"
    X10_A5          = "61"
    X10_A6          = "69"
    X10_A7          = "65"
    X10_A8          = "6D"
    X10_A9          = "67"
    X10_A10         = "6F"
    X10_A11         = "63"
    X10_A12         = "6B"
    X10_A13         = "60"
    X10_A14         = "68"
    X10_A15         = "64"
    X10_A16         = "6C"
    X10_AON         = "62"
    X10_AOFF        = "63"


def HexToByte( hexStr ):
    bytes = []
    hexStr = ''.join( hexStr.split(" ") )
    for i in range(0, len(hexStr), 2):
        bytes.append( chr( int (hexStr[i:i+2], 16 ) ) )
    return ''.join( bytes )


def ByteToHex( byteStr ):
    return ''.join( [ "%02X " % ord( x ) for x in byteStr ] ).strip()


def GetX10Address( deviceId ):
    if (deviceId == 1):
        return L.X10_A1
    elif (deviceId == 2):
        return L.X10_A2
    elif (deviceId == 3):
        return L.X10_A3
    elif (deviceId == 4):
        return L.X10_A4
    elif (deviceId == 5):
        return L.X10_A5
    elif (deviceId == 6):
        return L.X10_A6
    elif (deviceId == 7):
        return L.X10_A7
    elif (deviceId == 8):
        return L.X10_A8
    elif (deviceId == 9):
        return L.X10_A9
    elif (deviceId == 10):
        return L.X10_A10
    elif (deviceId == 11):
        return L.X10_A11
    elif (deviceId == 12):
        return L.X10_A12
    elif (deviceId == 13):
        return L.X10_A13
    elif (deviceId == 14):
        return L.X10_A14
    elif (deviceId == 15):
        return L.X10_A15
    elif (deviceId == 16):
        return L.X10_A16
    else:
        return "00"


class SerialProtocol(protocol.Protocol):
    buffer = ""
    bytesWritten = 0
    retries = 0
    cmd1Written = ""
    cmd2Written = ""
    mode = ""
    setpoint = ""
    messageWritten = ""
    x10command = ""
    msgDestination = ""
    timer = threading.Timer
    
    def clearBuffer(self):
        self.buffer = ""

    def threadSafeTimeout(self):
        self.d.errback(Exception("Timeout when communicating with device!"))

    def timeout(self):
        print "Timeout!!"
        self.cmd1Written = ""
        self.cmd2Written = ""
        reactor.callFromThread(self.threadSafeTimeout)
    
    def connectionMade(self):
        print "Connected to serial port.  Listening...\n"

    def connectionLost(self, reason):
        print "\n **** LOST CONNECTION TO SERIAL PORT!! **** \n"

    def dataReceived(self, data):
        print "Data received:     " + ByteToHex(data)
        self.buffer += data

        if (ByteToHex(self.buffer[0]) == L.NAK):
            # No echo in case of NAK
            self.bytesWritten -= 8
        elif (self.bytesWritten > 0):
            # Discard echoed characters
            temp = len(self.buffer)
            if (temp < self.bytesWritten):
                self.buffer = ""
                self.bytesWritten -= temp
            else:
                self.buffer = self.buffer[self.bytesWritten:]
                self.bytesWritten = 0

        if (len(self.buffer) > 0):
            print "Data buffer:       " + ByteToHex(self.buffer)
            message = self.parseMessage(self.buffer)
            if (message != None):
                self.buffer = self.buffer[len(message):]
                self.handleMessage(message)

    def parseMessage(self, buffer):
        if (ByteToHex(buffer[0]) == L.ACK or     # Message ACK
            ByteToHex(buffer[0]) == L.NAK):      # Message NAK
            return buffer[:1]

        if (len(buffer) < 2):
            return None

        if (ByteToHex(buffer[0]) == "02"):       # All Insteon Messages start with 02
            if (ByteToHex(buffer[1]) == "62"):   # Insteon Message
                if (len(buffer) >= 8):           # 8 Bytes Long
                    return buffer[:8]
            elif (ByteToHex(buffer[1]) == "50"): # Insteon Standard Message Received
                if (len(buffer) >= 11):          # 11 Bytes Long
                    return buffer[:11]
            elif (ByteToHex(buffer[1]) == "51"): # Insteon Extended Message Received
                if (len(buffer) >= 25):          # 25 Bytes Long
                    return buffer[:25]
            elif (ByteToHex(buffer[1]) == "52"): # X10 Message Received
                if (len(buffer) >= 4):           # 4 Bytes Long
                    return buffer[:4]

        return None

    def handleMessage(self, message):
        print "Handling message:  " + ByteToHex(message)
        try:
            if (ByteToHex(message) == L.ACK):
                self.retries = 0
                if (self.cmd1Written == L.CMD_X10ADDRESS):
                    self.timer.cancel()
                    self.cmd1Written = L.CMD_X10COMMAND
                    time.sleep(0.6)
                    self.writeMessage(self.x10command)
                elif (self.cmd1Written == L.CMD_X10COMMAND):
                    self.timer.cancel()
                    self.cmd1Written = ""
                    self.cmd2Written = ""
                    self.msgDestination = ""
                    time.sleep(0.6)
                    self.d.callback("ok")
                return
            elif (ByteToHex(message) == L.NAK):
                if (self.retries < 2):
                    print "GOT NAK - Retrying"
                    time.sleep(0.2)
                    self.timer.cancel()
                    self.writeMessage(self.messageWritten)
                    self.retries += 1
                else:
                    self.timer.cancel()
                    self.retries = 0
                    print "GOT NAK - Max retries reached!"
                    self.cmd1Written = ""
                    self.cmd2Written = ""
                    self.msgDestination = ""
                    self.d.errback(Exception("Retried 3 times - message NAK"))
                return
            
            # Verify fromAddress & toAddress & cmd for insteon commands
            hexMsg = ByteToHex(message)
            if (len(hexMsg) > 22):
                fromAddress = hexMsg[6:14]
                toAddress = hexMsg[15:23]
                cmd1 = hexMsg[27:29]
                if ((toAddress != L.PLM) or (fromAddress != self.msgDestination) or
                    ((self.cmd1Written != L.CMD_STATUS) and (cmd1 != self.cmd1Written))):
                    print "Invalid or stale message - discarding."
                    print "toAddress   = " + toAddress +   " | PLM address = " + L.PLM
                    print "fromAddress = " + fromAddress + " | message destination = " + self.msgDestination
                    print "cmd1 =        " + cmd1 +   "      | cmd written = " + self.cmd1Written
                    self.buffer = self.buffer[len(message):]
                    return
            
            resultStr = ""
            
            if ((self.cmd1Written == L.CMD_ON) or 
                (self.cmd1Written == L.CMD_OFF) or
                (self.cmd1Written == L.CMD_ALL_LINK and self.cmd2Written == L.CMD_ON) or
                (self.cmd1Written == L.CMD_ALL_LINK and self.cmd2Written == L.CMD_OFF) or
                (self.cmd1Written == L.CMD_SLOW_ON) or 
                (self.cmd1Written == L.CMD_SLOW_OFF) or
                (self.cmd1Written == L.CMD_T_SETCOOL) or
                (self.cmd1Written == L.CMD_T_SETHEAT) or
                (self.cmd1Written == L.CMD_T_ZONE_INFO and self.cmd2Written == L.CMD_TC_HEAT) or 
                (self.cmd1Written == L.CMD_T_ZONE_INFO and self.cmd2Written == L.CMD_TC_COOL) or 
                (self.cmd1Written == L.CMD_T_ZONE_INFO and self.cmd2Written == L.CMD_TC_AUTO) or 
                (self.cmd1Written == L.CMD_T_ZONE_INFO and self.cmd2Written == L.CMD_TC_FANON) or
                (self.cmd1Written == L.CMD_T_ZONE_INFO and self.cmd2Written == L.CMD_TC_FANOFF) or
                (self.cmd1Written == L.CMD_T_ZONE_INFO and self.cmd2Written == L.CMD_TC_ALLOFF) or
                (self.cmd1Written == L.CMD_T_ZONE_INFO and self.cmd2Written == L.CMD_TC_PROGHEAT) or
                (self.cmd1Written == L.CMD_T_ZONE_INFO and self.cmd2Written == L.CMD_TC_PROGCOOL) or
                (self.cmd1Written == L.CMD_T_ZONE_INFO and self.cmd2Written == L.CMD_TC_PROGAUTO)):
                resultStr = "ok"
            elif (self.cmd1Written == L.CMD_STATUS):
                resultStr = str(int(round((float(struct.unpack('=B', message[-1:])[0]) / 255) * 100)))
            elif (self.cmd1Written == L.CMD_T_CONTROL and self.cmd2Written == L.CMD_TC_AMBIENT):
                resultStr = str(int(round(float(struct.unpack('=B', message[-1:])[0]) / 2)))
            elif (self.cmd1Written == L.CMD_T_CONTROL and self.cmd2Written == L.CMD_TC_STATUS):
                result = int(struct.unpack('=B', message[-1:])[0])
                binaryStr = bin(result)
                if (binaryStr[2] == "1"):
                    resultStr = "cool"
                elif (binaryStr[3] == "1"):
                    resultStr = "heat"
                else:
                    resultStr = "off"
            elif (self.cmd1Written == L.CMD_T_CONTROL and self.cmd2Written == L.CMD_TC_GETMODE):
                if (int(struct.unpack('=B', message[-1:])[0]) == 1):
                    resultStr = "heat"
                elif (int(struct.unpack('=B', message[-1:])[0]) == 2):
                    resultStr = "cool"
                elif (int(struct.unpack('=B', message[-1:])[0]) == 3):
                    resultStr = "auto"
                elif (int(struct.unpack('=B', message[-1:])[0]) == 4):
                    resultStr = "fan"
                elif (int(struct.unpack('=B', message[-1:])[0]) == 5):
                    resultStr = "prog_auto"
                elif (int(struct.unpack('=B', message[-1:])[0]) == 6):
                    resultStr = "prog_heat"
                elif (int(struct.unpack('=B', message[-1:])[0]) == 7):
                    resultStr = "prog_cool"
                else:
                    resultStr = "off"
            elif (self.cmd1Written == L.CMD_T_ZONE_INFO and self.cmd2Written == L.CMD_TZ_SETPOINT):
                temp = str(int(round(float(struct.unpack('=B', message[-1:])[0]) / 2)))
                if ((self.setpoint == "") and (self.mode == "auto" or self.mode == "prog_auto")):
                    self.setpoint = temp + "."
                    return
                resultStr = self.setpoint + temp

            self.timer.cancel()
            self.cmd1Written = ""
            self.cmd2Written = ""
            self.msgDestination = ""
            print "Writing callback! Result = '" + resultStr + "'"
            self.d.callback(resultStr)

        except AlreadyCalledError:
            self.buffer = self.buffer[len(message):]
            print "Already called this callback - why?? Discarding this message."

    def writeMessage(self, message):
        print "Writing message:   " + message
        writeData = HexToByte(message)
        global ser
        try:
            ser.write(writeData)
        except:
            try:
                ser = SerialPort(serproto, '/dev/ttyUSB0', reactor, 19200)
                ser.write(writeData)
            except:
                raise
        self.bytesWritten += len(writeData)
        self.messageWritten = message
        self.timer = threading.Timer(4.0, self.timeout)
        self.timer.start()
        self.d = defer.Deferred()
        return self.d

    def TurnOn(self, deviceId, level=100):
        print "-- TurnOn (device='%s', level='%d')" % (deviceId, level)
        if (level > 100): level = 100
        lightLevel = ByteToHex(struct.pack('=B', int(round((float(level) / 100) * 255))))
        message = L.PREFIX + " " + L.INSTEON + " " + deviceId + " " + L.FLAGS + " " + L.CMD_ON + " " + lightLevel
        self.cmd1Written = L.CMD_ON
        self.msgDestination = deviceId
        return self.writeMessage(message)

    def TurnOff(self, deviceId):
        print "-- TurnOff (device='%s')" % deviceId
        message = L.PREFIX + " " + L.INSTEON + " " + deviceId + " " + L.FLAGS + " " + L.CMD_OFF + " " + "00"
        self.cmd1Written = L.CMD_OFF
        self.msgDestination = deviceId
        return self.writeMessage(message)

    def TurnOnGroup(self, deviceId, level=100):
        print "-- TurnOnGroup (device='%s', level='%d')" % (deviceId, level)
        if (level > 100): level = 100
        lightLevel = ByteToHex(struct.pack('=B', int(round((float(level) / 100) * 255))))
        message = L.PREFIX + " " + L.INSTEON + " " + deviceId + " " + L.EXT_FLAGS + " " + L.CMD_ALL_LINK + " 00 00 01 " + lightLevel + " " + L.CMD_ON + " " + lightLevel + " 00 00 00 00 00 00 00 00 00"
        self.cmd1Written = L.CMD_ALL_LINK
        self.cmd2Written = L.CMD_ON
        self.msgDestination = deviceId
        return self.writeMessage(message)

    def TurnOffGroup(self, deviceId):
        print "-- TurnOffGroup (device='%s')" % deviceId
        message = L.PREFIX + " " + L.INSTEON + " " + deviceId + " " + L.EXT_FLAGS + " " + L.CMD_ALL_LINK + " 00 00 01 00 " + L.CMD_OFF + " 00 00 00 00 00 00 00 00 00 00"
        self.cmd1Written = L.CMD_ALL_LINK
        self.cmd2Written = L.CMD_OFF
        self.msgDestination = deviceId
        return self.writeMessage(message)

    def TurnOnSlow(self, deviceId, level=100):
        print "-- TurnOnSlow (device='%s', level='%d')" % (deviceId, level)
        if (level > 100): level = 100
        lightLevel = int(round((float(level) / 100) * 15)) << 4
        rampRate = 12
        levelRamp = ByteToHex(struct.pack('=B', lightLevel | rampRate))
        message = L.PREFIX + " " + L.INSTEON + " " + deviceId + " " + L.FLAGS + " " + L.CMD_SLOW_ON + " " + levelRamp
        self.cmd1Written = L.CMD_SLOW_ON
        self.msgDestination = deviceId
        return self.writeMessage(message)

    def TurnOffSlow(self, deviceId):
        print "-- TurnOffSlow (device='%s')" % deviceId
        lightLevel = 0
        rampRate = 12
        levelRamp = ByteToHex(struct.pack('=B', lightLevel | rampRate))
        message = L.PREFIX + " " + L.INSTEON + " " + deviceId + " " + L.FLAGS + " " + L.CMD_SLOW_OFF + " " + levelRamp
        self.cmd1Written = L.CMD_SLOW_OFF
        self.msgDestination = deviceId
        return self.writeMessage(message)

    def GetStatus(self, deviceId):
        print "-- GetStatus (device='%s')" % deviceId
        message = L.PREFIX + " " + L.INSTEON + " " + deviceId + " " + L.FLAGS + " " + L.CMD_STATUS + " " + "00"
        self.cmd1Written = L.CMD_STATUS
        self.msgDestination = deviceId
        return self.writeMessage(message)

    def X10TurnOn(self, deviceId):
        print "-- X10TurnOn (device='%s')" % deviceId
        message = L.PREFIX + " " + L.X10 + " " + GetX10Address(int(deviceId)) + " " + L.CMD_X10ADDRESS
        self.cmd1Written = L.CMD_X10ADDRESS
        self.x10command = L.PREFIX + " " + L.X10 + " " + L.X10_AON + " " + L.CMD_X10COMMAND
        return self.writeMessage(message)

    def X10TurnOff(self, deviceId):
        print "-- X10TurnOff (device='%s')" % deviceId
        message = L.PREFIX + " " + L.X10 + " " + GetX10Address(int(deviceId)) + " " + L.CMD_X10ADDRESS
        self.cmd1Written = L.CMD_X10ADDRESS
        self.x10command = L.PREFIX + " " + L.X10 + " " + L.X10_AOFF + " " + L.CMD_X10COMMAND
        return self.writeMessage(message)

    def TempGetAmbient(self, deviceId):
        print "-- TempGetAmbient (device='%s')" % deviceId
        message = L.PREFIX + " " + L.INSTEON + " " + deviceId + " " + L.THERM_FLAGS + " " + L.CMD_T_CONTROL + " " + L.CMD_TC_AMBIENT
        self.cmd1Written = L.CMD_T_CONTROL
        self.cmd2Written = L.CMD_TC_AMBIENT
        self.msgDestination = deviceId
        return self.writeMessage(message)

    def TempGetStatus(self, deviceId):
        print "-- TempGetStatus (device='%s')" % deviceId
        message = L.PREFIX + " " + L.INSTEON + " " + deviceId + " " + L.THERM_FLAGS + " " + L.CMD_T_CONTROL + " " + L.CMD_TC_STATUS
        self.cmd1Written = L.CMD_T_CONTROL
        self.cmd2Written = L.CMD_TC_STATUS
        self.msgDestination = deviceId
        return self.writeMessage(message)

    def TempGetMode(self, deviceId):
        print "-- TempGetMode (device='%s')" % deviceId
        message = L.PREFIX + " " + L.INSTEON + " " + deviceId + " " + L.THERM_FLAGS + " " + L.CMD_T_CONTROL + " " + L.CMD_TC_GETMODE
        self.cmd1Written = L.CMD_T_CONTROL
        self.cmd2Written = L.CMD_TC_GETMODE
        self.msgDestination = deviceId
        return self.writeMessage(message)

    def TempSetMode(self, deviceId, mode):
        print "-- TempSetMode (device='%s')" % deviceId
        message = L.PREFIX + " " + L.INSTEON + " " + deviceId + " " + L.THERM_FLAGS + " " + L.CMD_T_CONTROL + " "
        self.cmd1Written = L.CMD_T_CONTROL
        if (mode == "heat"):
            message += L.CMD_TC_HEAT
            self.cmd2Written = L.CMD_TC_HEAT
        elif (mode == "cool"):
            message += L.CMD_TC_COOL
            self.cmd2Written = L.CMD_TC_COOL
        elif (mode == "auto"):
            message += L.CMD_TC_AUTO
            self.cmd2Written = L.CMD_TC_AUTO
        elif (mode == "fan_on"):
            message += L.CMD_TC_FANON
            self.cmd2Written = L.CMD_TC_FANON
        elif (mode == "fan_auto"):
            message += L.CMD_TC_FANOFF
            self.cmd2Written = L.CMD_TC_FANOFF
        elif (mode == "off"):
            message += L.CMD_TC_ALLOFF
            self.cmd2Written = L.CMD_TC_ALLOFF
        elif (mode == "prog_heat"):
            message += L.CMD_TC_PROGHEAT
            self.cmd2Written = L.CMD_TC_PROGHEAT
        elif (mode == "prog_cool"):
            message += L.CMD_TC_PROGCOOL
            self.cmd2Written = L.CMD_TC_PROGCOOL
        elif (mode == "prog_auto"):
            message += L.CMD_TC_PROGAUTO
            self.cmd2Written = L.CMD_TC_PROGAUTO
        else:
            return "error"
        self.msgDestination = deviceId
        return self.writeMessage(message)

    def TempGetSetpoint(self, deviceId, mode):
        print "-- TempGetSetpoint (device='%s')" % deviceId
        message = L.PREFIX + " " + L.INSTEON + " " + deviceId + " " + L.THERM_FLAGS + " " + L.CMD_T_ZONE_INFO + " " + L.CMD_TZ_SETPOINT
        self.cmd1Written = L.CMD_T_ZONE_INFO
        self.cmd2Written = L.CMD_TZ_SETPOINT
        self.mode = mode
        self.setpoint = ""
        self.msgDestination = deviceId
        return self.writeMessage(message)

    def TempSetCool(self, deviceId, temp):
        print "-- TempSetCool (device='%s')" % deviceId
        temperature = ByteToHex(struct.pack('=B', int(temp)*2))
        message = L.PREFIX + " " + L.INSTEON + " " + deviceId + " " + L.THERM_FLAGS + " " + L.CMD_T_SETCOOL + " " + temperature
        self.cmd1Written = L.CMD_T_SETCOOL
        self.msgDestination = deviceId
        return self.writeMessage(message)

    def TempSetHeat(self, deviceId, temp):
        print "-- TempSetHeat (device='%s')" % deviceId
        temperature = ByteToHex(struct.pack('=B', int(temp)*2))
        message = L.PREFIX + " " + L.INSTEON + " " + deviceId + " " + L.THERM_FLAGS + " " + L.CMD_T_SETHEAT + " " + temperature
        self.cmd1Written = L.CMD_T_SETHEAT
        self.msgDestination = deviceId
        return self.writeMessage(message)

    def Test1(self, deviceId, level=100):
        print "-- Test 1 (device='%s', level='%d')" % (deviceId, level)
        if (level > 100): level = 100
        lightLevel = ByteToHex(struct.pack('=B', int(round((float(level) / 100) * 255))))
        message = "02 62 14 AC 5E 1F 30 00 " + "00 01 FF 11 FF 00 00 00 00 00 00 00 00 00"
        self.cmd1Written = L.CMD_ON
        self.msgDestination = deviceId
        return self.writeMessage(message)

    def Test2(self, deviceId):
        print "-- Test 2 (device='%s')" % deviceId
        message = "02 62 12 BD 52 1F 2E 00 " + "00 00 00 00 00 00 00 00 00 00 00 00 00 00"
        self.cmd1Written = L.CMD_ON
        self.msgDestination = deviceId
        return self.writeMessage(message)

    def Test3(self, deviceId):
        print "-- Test 3 (device='%s')" % deviceId
        message = "02 62 14 AC 5E 1F 30 00 " + "00 01 00 13 00 00 00 00 00 00 00 00 00 00"
        self.cmd1Written = L.CMD_OFF
        self.msgDestination = deviceId
        return self.writeMessage(message)



class LightProtocol(basic.LineReceiver):
    def connectionMade(self):
        print "## TCP client connected!"

    def connectionLost(self, reason):
        print "## TCP client disconnected!"
        
    def lineReceived(self, data):
        def onError(err):
            global processing, queue
            message = "error: " + err.getErrorMessage()
            if (queue.empty() == False):
                reactor.callFromThread(self.lineReceived, queue.get())
                print "Processing message in Queue"
            processing = False
            return message
        def writeResponse(message):
            global processing, queue
            self.transport.write(message + "\r\n")
            if (queue.empty() == False):
                reactor.callFromThread(self.lineReceived, queue.get())
                print "Processing message in Queue"
            processing = False

        global processing, queue
        if (processing):
            queue.put(data)
            print "Queueing message!"
            return

        processing = True
        command = data.split('.')
        
        print "lineReceived() " + data
        serproto.clearBuffer()
        
        # Light Commands
        if (command[0] == "on"):
            if (len(command) > 2):
                d = serproto.TurnOn(command[1], int(command[2]))
            else:
                d = serproto.TurnOn(command[1])                
        elif (command[0] == "off"):
            d = serproto.TurnOff(command[1])
        elif (command[0] == "ongroup"):
            if (len(command) > 2):
                d = serproto.TurnOnGroup(command[1], int(command[2]))
            else:
                d = serproto.TurnOnGroup(command[1])                
        elif (command[0] == "offgroup"):
            d = serproto.TurnOffGroup(command[1])
        elif (command[0] == "slow_on"):
            if (len(command) > 2):
                d = serproto.TurnOnSlow(command[1], int(command[2]))
            else:
                d = serproto.TurnOnSlow(command[1])                
        elif (command[0] == "slow_off"):
            d = serproto.TurnOffSlow(command[1])
        elif (command[0] == "status"):
            d = serproto.GetStatus(command[1])
        elif (command[0] == "x10on"):
            d = serproto.X10TurnOn(command[1])
        elif (command[0] == "x10off"):
            d = serproto.X10TurnOff(command[1])
        elif (command[0] == "test"):
            d = serproto.Test1("")
        elif (command[0] == "test2"):
            d = serproto.Test2("")
        elif (command[0] == "test3"):
            d = serproto.Test3("")

        # Temperature commands
        elif (command[0] == "temp_get_ambient"):
            d = serproto.TempGetAmbient(command[1])
        elif (command[0] == "temp_get_status"):
            d = serproto.TempGetStatus(command[1])
        elif (command[0] == "temp_get_mode"):
            d = serproto.TempGetMode(command[1])
        elif (command[0] == "temp_set_mode"):
            d = serproto.TempSetMode(command[1], command[2])
        elif (command[0] == "temp_get_setpoint"):
            d = serproto.TempGetSetpoint(command[1], command[2])
        elif (command[0] == "temp_set_cool"):
            d = serproto.TempSetCool(command[1], command[2])
        elif (command[0] == "temp_set_heat"):
            d = serproto.TempSetHeat(command[1], command[2])
        else:
            processing = False
            return

        d.addErrback(onError)
        d.addCallback(writeResponse)

class LightFactory(protocol.ServerFactory):
    protocol = LightProtocol

queue = Queue.Queue(0)
processing = False
serproto = SerialProtocol()
ser = SerialPort(serproto, '/dev/ttyUSB0', reactor, 19200)
reactor.listenTCP(1234, LightFactory())
reactor.run()

