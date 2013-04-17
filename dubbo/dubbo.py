#!/usr/python
#coding=utf-8
import json
import socket
import protocol
import hessian2
import threading
import thread
import Queue
import java
import json
import types
import datetime
import time
import traceback

__version__ = '0.1.0'

RpcContent = threading.local()

class Future(object) :
    FUTURES = {}
    FUTURES_LOCK = threading.Lock()
    def __init__(self, request, timeout = 1) :
        self.id = request.rid
        self.timeout = timeout
        self.lock = threading.Lock()
        self.cond = threading.Condition(self.lock)
        self.reqeust = request
        self.response = None
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
        while True :
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
                time.sleep(0.03)
            except Exception, e:
                print 'check timeout loop' + str(e)

thread.start_new_thread(Future._checkTimeoutLoop, ())

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
            print 'already reconnection'
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

class DubboClient(object) :
    def __init__(self, addr) :
        self.addr = addr
        self.endpoint = Endpoint(addr, self.__recvResponse)
        self.endpoint.start()
    
    def invoke(self, request) :
        data = protocol.encodeRequest(request)
        timeout = request.data.attachments['timeout']
        future = Future(request, timeout)
        self.endpoint.send(data)
        return future.get()

    def __recvResponse(self, header, data) :
        response = protocol.decode(header, data)
        if response.isEvent : 
            return
        Future.received(response)

class DubboProxy(object) :
    def __init__(self, client, classInfo, attachments) :
        self.client = client
        self.classInfo = classInfo
        self.attachments = attachments
        if 'method' in attachments :
            self.methodConfig = attachments['method']
            del attachments['method']
        else :
            self.methodConfig = {}

    def invoke(self, name, args) :
        if not name in self.classInfo.methodMap :
            raise KeyError('interface ' + self.classInfo.thisClass + ' has no method name ' + str(name))
        methods = self.classInfo.methodMap[name]
        if len(methods) > 1 :
            method = self.__guessMethod(methods, args)
            if method == None :
                errorStr = 'can not find match method : ' + \
                        self.classInfo.thisClass + '.' + name + '(' + \
                        ', '.join([type(arg) for arg in args]) + \
                        ') maybe : '
                for method in methods :
                    errorStr += self.classInfo.thisClass + '.' + name + '(' + \
                            ', '.join(java.analyseParamTypes(self.__getParamType(method))) + \
                            ')'
                raise KeyError(errorStr)
        else :
            method = methods[0]
        
        paramType = self.__getParamType(method)

        request = protocol.DubboRequest()
        attachments = self.attachments.copy()
        if name in self.methodConfig :
            attachments.update(self.methodConfig[name])
        #print name, paramType, '(' + ', '.join([str(arg) for arg in args]) + ')', self.attachments
        data = protocol.RpcInvocation(name, paramType, args, attachments)
        request.data = data
        return self.client.invoke(request)

    def __guessMethod(self, methods, args) :
        for method in methods :
            paramTypes = java.analyseParamTypes(self.__getParamType(method))
            if len(paramTypes) != len(args) :
                continue
            ok = True
            for i in range(len(paramTypes)) :
                pType = type(args[i])
                jType = paramTypes[i]
                if \
                    (pType == types.BooleanType and jType == 'bool') \
                    or (pType == types.DictType and jType == 'dict') \
                    or (pType == types.FloatType and jType == 'float') \
                    or (pType == types.IntType and jType == 'int') \
                    or (pType == types.IntType and jType == 'long') \
                    or (pType == types.ListType and jType == 'list') \
                    or (pType == types.LongType and jType == 'long') \
                    or (pType == types.StringType and jType == 'string') \
                    or (pType == types.TupleType and jType == 'list') \
                    or (pType == types.UnicodeType and jType == 'string') \
                    or (pType == hessian2.Object and jType == args[i]._metaType) \
                    or (pType == hessian2.Binary and jType == 'byte') :
                    continue
                elif pType == types.NoneType :
                    continue
                else :
                    ok = False
                    break
            if ok :
                return method
        return None

    def __getParamType(self, method) :
        paramType = self.classInfo.constantPool[method['descriptorIndex']][2]
        paramType = paramType[paramType.find('(') + 1 : paramType.find(')')]
        return paramType

    def __getattr__(self, name) :
        def dubbo_invoke(*args) :
            return self.invoke(name, args)
        return dubbo_invoke

class Dubbo(object):
    def __init__(self, addr, classPath = None, owner = None, customer = None, organization = None, config = None):
        self.client = DubboClient(addr)
        self.javaClassLoader = java.JavaClassLoader(classPath)
        owner = owner or 'pythonGuest'
        customer = customer or 'consumer-of-python-dubbo'
        self.organization = organization or ''
        self.attachments = {'owner' : owner, 'customer' : customer}
        self.config = config or {}
        if self.config :
            for key, value in self.config.items() :
                if key == 'reference' :
                    continue
                self.attachments[key] = value
        if 'reference' not in self.config :
            self.config['reference'] = {}

    def getProxy(self, interface, **args) :
        classInfo = self.javaClassLoader.findClass(interface)
        if classInfo == None :
            return None
        attachments = self.attachments.copy()
        attachments['path'] = interface
        attachments['interface'] = interface

        if interface in self.config['reference'] :
            attachments.update(self.config['reference'][interface])

        if args :
            for key, value in args.items() :
                attachments[key] = value

        self.__checkAttachments(attachments)

        return DubboProxy(self.client, classInfo, attachments)

    def __checkAttachments(self, attachments) :
        if 'timeout' not in attachments :
            attachments['timeout'] = 1
        if 'version' not in attachments :
            attachments['version'] = '1.0.0'

def __JsonDefault(obj): 
    if isinstance(obj, datetime.datetime) : 
        return obj.strftime('%Y-%m-%dT%H:%M:%S') 
    elif isinstance(obj, datetime.date) : 
        return obj.strftime('%Y-%m-%d') 
    elif isinstance(obj, hessian2.Object) :
        return obj.__dict__
    else: 
        raise TypeError('%r is not JSON serializable' % obj) 

def formatObject(obj) :
    return json.dumps(obj, ensure_ascii=False, indent=2, default = __JsonDefault)

outQueue = Queue.Queue()

def th(proxy, index) :
    while True :
        try :
            outQueue.put(str(index) + ' ' + str(len(formatObject(proxy.getBookUserIds([719791, 719827, 719844])))))
            time.sleep(1)
        except :
            print 'call error'

def pth() :
    while True :
        msg = outQueue.get()
        print msg

if __name__ == '__main__' :
    client = Dubbo(('localhost', 20880), '../travel-service-interface-1.5.3.jar', owner = 'you.zhou', customer = 'consumer-of-travel-book')

    proxy = client.getProxy('com.qunar.travel.book.service.ITravelBookService2', timeout = 0.5)

    #thread.start_new_thread(pth, ())

    #for i in range(10) :
    #    thread.start_new_thread(th, (proxy, i))
    #time.sleep(100000)
    print formatObject(proxy.getBookUserIds([719791, 719827, 719844]))
    #antispamService = client.getProxy('com.qunar.travel.antispam.service.IAntispamService')

    #print formatObject(antispamService.check([u'你好江泽民', u'64', u'呵呵']))

    #sortE = hessian2.Object('com.qunar.travel.query.param.SortDir', {'name' : 'DESC'})

    #print formatObject(proxy.getBookList('5763120@qunar', 0, 10, 1, sortE))

    #print proxy.getTravelBookDetail(692327L)

    #print proxy.clearCache(692327L)

    #proxy = client.getProxy('com.qunar.travel.destination.service.ITravelAlbumService', timeout = 3000)

    #print formatObject(proxy.findTravelAlbum(299914, 0, 10))
