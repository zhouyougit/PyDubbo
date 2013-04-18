import time
import threading
import heapq

class Task(object) :
    def __init__(self, cmd, initialDelay, period) :
        self.cmd = cmd
        self.initialDelay = initialDelay
        self.period = period
        self.lastTime = time.time()

    def getNextTime(self) :
        if self.initialDelay != -1 :
            return self.initialDelay + self.lastTime
        elif self.period != -1 :
            return self.period + self.lastTime
        else :
            raise ValueError('task initialDelay or period value error')

    def fire(self) :
        try :
            self.cmd()
        except Exception, e:
            print 'task fire raise an exception : ' + str(e)

class Scheduler(threading.Thread) :
    def __init__(self) :
        threading.Thread.__init__(self)
        self.queue = []
        self.lock = threading.Lock()
        self.cond = threading.Condition(self.lock)
        self.isRun = True

    def schedule(self, cmd, initialDelay, period) :
        task = Task(cmd, initialDelay, period)
        return self.scheduleTask(task)

    def scheduleTask(self, task) :
        with self.lock :
            heapq.heappush(self.queue, (task.getNextTime(), task))
            self.cond.notifyAll()
        return task

    def remove(self, task) :
        with self.lock :
            for i in range(len(self.queue)) :
                if task is self.queue[i][1] :
                    del self.queue[i]
                    break

    def run(self) :
        while self.isRun :
            try :
                with self.lock :
                    if not self.queue :
                        self.cond.wait(60)
                        continue
                    nextTime, task = heapq.nsmallest(1, self.queue)[0]
                    if nextTime > time.time() :
                        self.cond.wait(abs(time.time() - nextTime))
                        continue
                    heapq.heappop(self.queue)
                    if task.initialDelay != -1 :
                        task.initialDelay = -1
                    if task.period != -1 :
                        task.lastTime = time.time()
                        heapq.heappush(self.queue, (task.getNextTime(), task))
                task.fire()
            except Exception, e:
                print e

    def stop(self) :
        self.isRun = False
        with self.lock :
            self.cond.notifyAll()

