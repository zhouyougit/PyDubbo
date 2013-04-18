import protocol
import threading
import thread
import socket
import Queue
import time
from _utils import *

class Future(object) :
    FUTURES = {}
    FUTURES_LOCK = threading.Lock()
    def __init__(self, request, timeout, channel) :
        self.id = request.rid
        self.timeout = timeout
        self.lock = threading.Lock()
        self.cond = threading.Condition(self.lock)
        self.reqeust = request
        self.response = None
        self.channel = channel
        self.timestamp = time.time()
        Future.FUTURES_LOCK.acquire()
        try :
            Future.FUTURES[self.id] = self
        finally :
            Future.FUTURES_LOCK.release()

    def get(self) :
        return self.getWithTimeout(self.timeout)
    
    def getWithTimeout(self, timeout) :
        if self.isDone() :
            return self.__doReturn()
        with self.lock :
            if not self.isDone() :
                self.cond.wait(self.timeout)
                if not self.isDone() :
                    raise protocol.DubboTimeoutException('waiting response timeout. elapsed :' + str(self.timeout))

        return self.__doReturn()

    def setCallback(self, callback) :
        pass

    def isDone(self) :
        return self.response != None

    @classmethod
    def received(cls, response) :
        if response.rid in cls.FUTURES :
            Future.FUTURES_LOCK.acquire()
            try :
                if response.rid in cls.FUTURES :
                    future = Future.FUTURES[response.rid]
                    del Future.FUTURES[response.rid]
                else :
                    return
            finally :
                Future.FUTURES_LOCK.release()
            future.doReceived(response)

    def doReceived(self, response) :
        with self.lock :
            self.response = response
            self.cond.notifyAll()

    def __doReturn(self) :
        if self.response.status != protocol.DubboResponse.OK :
            raise protocol.DubboException('DubboException : status = ' + \
                    str(self.response.status) + ' errorMsg = ' + \
                    str(self.response.errorMsg))
        elif self.response.exception != None :
            raise protocol.DubboException(self.response.exception)
        else :
            return self.response.result

    @classmethod
    def _checkTimeoutLoop(cls) :
        try :
            for future in Future.FUTURES.values() :
                if future.isDone() :
                    continue
                if (time.time() - future.timestamp) > future.timeout :
                    print 'find timeout future'
                    response = protocol.DubboResponse(future.id)
                    response.status = protocol.DubboResponse.SERVER_TIMEOUT
                    response.seterrorMsg = 'waiting response timeout. elapsed :' + str(future.timeout)
                    Future.received(response)
        except Exception, e:
            print 'check timeout loop' + str(e)

class Endpoint(object) :
    def __init__(self, addr, readHandler) :
        self.addr = addr
        self.readHandler = readHandler
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.queue = Queue.Queue()
        self.lock = threading.Lock()
        self.cTime = None

    def start(self) :
        self.sock.connect(self.addr)
        self.cTime = time.time()
        thread.start_new_thread(self.__sendLoop, ())
        thread.start_new_thread(self.__recvLoop, ())

    def send(self, data) :
        self.queue.put(data)

    def __sendLoop(self) :
        while True :
            try :
                data = self.queue.get()
                self.sock.sendall(data)
            except Exception, e :
                print 'send error'
                self.__reconnection()

    def __reconnection(self) :
        if not self.lock.acquire(False) :
            self.lock.acquire()
            self.lock.release()
            return
        try :
            print 'start reconnection'
            while True :
                try :
                    print 'start shutdown'
                    try :
                        self.sock.shutdown(socket.SHUT_RDWR)
                    except :
                        pass
                    print 'finish shutdown'
                    del self.sock
                    print 'create new socket'
                    self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    print 'create new socket finish'
                    self.cTime = time.time()
                    print 'start connect'
                    self.sock.connect(self.addr)
                    print 'finish connect'
                    break
                except socket.error :
                    if time.time() - self.cTime < 2 :
                        time.sleep(2)
        finally :
            self.lock.release()
        print 'end reconnection'

    def __recv(self, length) :
        while True :
            data = self.sock.recv(length)
            if not data :
                print 'recv error'
                self.__reconnection()
                continue
            return data

    def __recvLoop(self) :
        while True :
            try :
                header = self.__recv(protocol.HEADER_LENGTH)
                if header[:2] != protocol.MAGIC_NUMBER :
                    continue
                while len(header) < protocol.HEADER_LENGTH :
                    temp = self.__recv(protocol.HEADER_LENGTH - len(header))
                    header += temp
                dataLength = protocol.getDataLength(header)
                data = ''
                while len(data) < dataLength :
                    temp = self.__recv(dataLength - len(data))
                    data += temp
                self.readHandler(header, data)
            except Exception, e :
                print 'recv loop' + str(e)

class DubboChannel(object) :
    def __init__(self, addr) :
        self.addr = addr
        self.endpoint = Endpoint(addr, self.__recvResponse)
        self.endpoint.start()
        self.lastReadTime = time.time()
        self.lastWriteTime = time.time()
    
    def send(self, message) :
        if isinstance(message, protocol.DubboRequest) :
            data = protocol.encodeRequest(message)
        else :
            data = protocol.encodeResponse(message)

        self.lastWriteTime = time.time()
        self.endpoint.send(data)

    def __recvResponse(self, header, data) :
        self.lastReadTime = time.time()
        print '---- header ----'
        printByteStr(header)
        print '---- body ----'
        printByteStr(data)
        print '---- end ----'
        obj = protocol.decode(header, data)
        if isinstance(obj, protocol.DubboRequest) :
            request = obj
            if request.isHeartbeat :
                response = protocol.DubboResponse(request.rid)
                response.isEvent = True
                response.isHeartbeat = True
                self.send(response)
            else :
                raise Exception('unimplement recv data request')
        else :
            response = obj
            if response.isHeartbeat : 
                return
            Future.received(response)
