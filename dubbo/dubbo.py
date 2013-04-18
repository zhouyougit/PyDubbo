#!/usr/python
#coding=utf-8
import json
import protocol
import hessian2
import threading
import thread
import Queue
import types
import json
import datetime
import time
import random

import java
from constants import *
import _model
from _utils import *
from _net import *
import scheduler

__version__ = '0.1.0'

RpcContext = threading.local()

scheduledExecutor = scheduler.Scheduler()
scheduledExecutor.start()

scheduledExecutor.schedule(Future._checkTimeoutLoop, \
        DEFAULT_FUTURE_CHECK_PERIOD, DEFAULT_FUTURE_CHECK_PERIOD)

def _getRequestParam(request, key, default = None) :
    if key in request.data.attachments :
        return request.data.attachments[key]
    return default

class DubboClient(object) :
    def __init__(self, addrs, config) :
        self.channels = []
        for addr in addrs :
            self.channels.append(DubboChannel(addr))

        if config and KEY_HEARTBEAT in config :
            self.heartbeat = config[KEY_HEARTBEAT]
        else :
            self.heartbeat = DEFAULT_HEARTBEAT

        scheduledExecutor.schedule(self.__heartbeatCheck, self.heartbeat, self.heartbeat)
    
    def invoke(self, rpcInvocation) :
        request = protocol.DubboRequest()
        request.data = rpcInvocation
        
        channel = self.__selectChannel(request)

        timeout = _getRequestParam(request, KEY_TIMEOUT)
        withReturn = _getRequestParam(request, KEY_WITH_RETURN, True)
        async = _getRequestParam(request, KEY_ASYNC, False)
        
        if not withReturn :
            channel.send(data)
            return
        
        if async :
            future = Future(request, timeout, channel)
            RpcContext.future = future
            channel.send(request)
            return
        else :
            future = Future(request, timeout, channel)
            channel.send(request)
            return future.get()

    def __selectChannel(self, request) :
        index = random.randint(0, len(self.channels) - 1)
        return self.channels[index]

    def __heartbeatCheck(self) :
        now = time.time()
        for channel in self.channels :
            if now - channel.lastReadTime > self.heartbeat \
                    or now - channel.lastWriteTime > self.heartbeat :
                request = protocol.DubboRequest()
                request.isEvent = True
                request.isHeartbeat = True
                channel.send(request)

class ServiceProxy(object) :
    def __init__(self, client, classInfo, attachments) :
        self.client = client
        self.classInfo = classInfo
        self.attachments = attachments
        if KEY_METHOD in attachments :
            self.methodConfig = attachments[KEY_METHOD]
            del attachments[KEY_METHOD]
        else :
            self.methodConfig = {}

    def _updateConfig(self, config) :
        config = config.copy()
        if KEY_METHOD in config :
            methodConfig = config[KEY_METHOD]
            del config[KEY_METHOD]
        else :
            methodConfig = None
        self.attachments.update(config)
        if methodConfig :
            for methodName, methodConfig in methodConfig.items() :
                if methodName not in self.methodConfig :
                    self.methodConfig[methodName] = methodConfig.copy()
                else :
                    self.methodConfig[methodName].update(methodConfig)

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

        attachments = self.attachments.copy()
        if name in self.methodConfig :
            attachments.update(self.methodConfig[name])
        print attachments
        #print name, paramType, '(' + ', '.join([str(arg) for arg in args]) + ')', self.attachments
        invocation = protocol.RpcInvocation(name, paramType, args, attachments)
        return self.client.invoke(invocation)

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
                    or (pType == _model.Object and jType == args[i]._metaType) \
                    or (pType == _model.Binary and jType == 'byte') :
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

def _getAndDelConfigParam(config, key, default = None) :
    if config and key in config :
        value = config[key]
        del config[key]
        return value
    else :
        return default

class Dubbo(object):
    def __init__(self, addrs, config = None):
        if config :
            config = config.copy()
        else :
            config = {}
        self.config = config

        classpath = _getAndDelConfigParam(config, KEY_CLASSPATH)
        self.javaClassLoader = java.JavaClassLoader(classpath)

        owner = _getAndDelConfigParam(config, KEY_DUBBO_OWNER, DEFAULT_DUBBO_OWNER)
        customer = _getAndDelConfigParam(config, KEY_DUBBO_CUSTOMER, DEFAULT_DUBBO_CUSTOMER)
        self.attachments = {KEY_OWNER : owner, KEY_CUSTOMER : customer}
        
        for key, value in self.config.items() :
            if key == KEY_REFERENCE :
                continue
            self.attachments[key] = value

        if KEY_REFERENCE not in self.config :
            self.config[KEY_REFERENCE] = {}
        
        self.client = DubboClient(addrs, self.config)

    def getProxy(self, interface, **args) :
        classInfo = self.javaClassLoader.findClassInfo(interface)
        if classInfo == None :
            return None
        attachments = self.attachments.copy()
        attachments[KEY_PATH] = interface
        attachments[KEY_INTERFACE] = interface

        if interface in self.config[KEY_REFERENCE] :
            attachments.update(self.config[KEY_REFERENCE][interface])

        if args :
            for key, value in args.items() :
                attachments[key] = value

        self.__checkAttachments(attachments)

        return ServiceProxy(self.client, classInfo, attachments)

    def createConstObjectFromClass(self, className) :
        return self.javaClassLoader.createConstObject(className)

    def __checkAttachments(self, attachments) :
        if KEY_TIMEOUT not in attachments :
            attachments[KEY_TIMEOUT] = DEFAULT_TIMEOUT
        if KEY_VERSION not in attachments :
            attachments[KEY_VERSION] = DEFAULT_SERVICE_VERSION

    def close(self) :
        scheduledExecutor.stop()

outQueue = Queue.Queue()

def th(proxy, index) :
    while True :
        try :
            proxy.getBookUserIds([719791, 719827, 719844])
            result = RpcContext.future.get()
            outQueue.put(str(index) + ' ' + str(len(formatObject(result))))
            time.sleep(1)
        except :
            print 'call error'

def pth() :
    while True :
        msg = outQueue.get()
        print msg

if __name__ == '__main__' :
    config = { \
            'owner' : 'pythonUser', \
            'customer' : 'consumer-of-python', \
            'classpath' : '../travel-service-interface-1.5.3.jar', \
            'reference' : { \
                'com.qunar.travel.book.service.ITravelBookService2' : { \
                    'method' : { \
                        'getBookUserIds' : {
                            'async' : True
                        },
                    }
                }
            }
        }
    client = Dubbo((('localhost', 20880),), config)

    proxy = client.getProxy('com.qunar.travel.book.service.ITravelBookService2', timeout = 0.5)
    start = time.time()
    result = proxy.getBookUserIds([719791, 719827, 719844])
    print result
    print formatObject(RpcContext.future.get())

    print formatObject(proxy.getTravelBookOverView(719791))
    print 'sleep'
    '''
    thread.start_new_thread(pth, ())

    for i in range(10) :
        thread.start_new_thread(th, (proxy, i))
    time.sleep(100000)
    
    result = []
    for i in range(100) :
        proxy.getBookUserIds([719791, 719827, 719844])
        result.append(RpcContext.future)

    for result in result :
        print formatObject(result.get())

    for i in range(100) :
        print formatObject(proxy.getBookUserIds([719791, 719827, 719844]))
    '''
    print time.time() - start

    client.close()

    #antispamService = client.getProxy('com.qunar.travel.antispam.service.IAntispamService')

    #print formatObject(antispamService.check([u'你好江泽民', u'64', u'呵呵']))

    #sortE = _model.Object('com.qunar.travel.query.param.SortDir', {'name' : 'DESC'})

    #print formatObject(proxy.getBookList('5763120@qunar', 0, 10, 1, sortE))

    #print proxy.getTravelBookDetail(692327L)

    #print proxy.clearCache(692327L)

    #proxy = client.getProxy('com.qunar.travel.destination.service.ITravelAlbumService', timeout = 3000)

    #print formatObject(proxy.findTravelAlbum(299914, 0, 10))
