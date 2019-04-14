
from __future__ import print_function
from pyspark.streaming import StreamingContext
from pyspark import SparkContext, SparkConf
import sys
from datetime import datetime
from pyspark.streaming.kafka import KafkaUtils
from kafka import KafkaProducer
import operator
import json
from collections import Counter
from nltk.corpus import stopwords
import string


class KafkaProducerWrapper(object):
    producer = None

    @staticmethod
    def getProducer(brokerList):
        if KafkaProducerWrapper.producer == None:
            KafkaProducerWrapper.producer = KafkaProducer(bootstrap_servers=brokerList, key_serializer=str.encode, value_serializer=str.encode)
        return KafkaProducerWrapper.producer


if __name__ == "__main__":
    # used for connecting to Kafka
    brokerList = ""
    # Spark checkpoint directory
    checkpointDir = ""
    # Kafka topic for reading log messages
    logsTopic = "mytweets"
    # Kafka topic for writing the calculated statistics
    statsTopic = "stats"
    # Session timeout in milliseconds
    SESSION_TIMEOUT_MILLIS = 2 * 60 * 1000  # 2 minutes
    # Number of RDD partitions to use
    numberPartitions = 3

    def printUsageAndExit():
        print("Usage: StreamingLogAnalyzer.py -brokerList=<kafka_host1:port1,...> -checkpointDir=HDFS_DIR [options]\n" +
              "\n" +
              "Options:\n" +
              " -inputTopic=NAME            Input Kafka topic name for reading logs data. Default is 'weblogs'.\n" +
              " -outputTopic=NAME        Output Kafka topic name for writing aggregated statistics. Default is 'stats'.\n" +
              " -sessionTimeout=NUM     Session timeout in minutes. Default is 2.\n" +
              " -numberPartitions=NUM Number of partitions for the streaming job. Default is 3.\n")
        sys.exit(1)

    def parseAndValidateArguments(args):
        global brokerList, checkpointDir, logsTopic, statsTopic, SESSION_TIMEOUT_MILLIS, numberPartitions
        try:
            for arg in args[1:]:
                if arg.startswith("-brokerList="):
                    brokerList = arg[12:]
                elif arg.startswith("-checkpointDir="):
                    checkpointDir = arg[15:]
                elif arg.startswith("-inputTopic="):
                    logsTopic = arg[12:]
                elif arg.startswith("-outputTopic="):
                    statsTopic = arg[13:]
                elif arg.startswith("-sessionTimeout="):
                    SESSION_TIMEOUT_MILLIS = int(arg[16:]) * 60 * 1000
                elif arg.startswith("-numberPartitions="):
                    numberPartitions = int(arg[18:])
                else:
                    printUsageAndExit()
        except Exception as e:
            print(e)
            printUsageAndExit()

        if (brokerList == "" or checkpointDir == "" or logsTopic == "" or statsTopic == "" or SESSION_TIMEOUT_MILLIS < 60 * 1000 or numberPartitions < 1):
            printUsageAndExit()

    conf = SparkConf()
    conf.setAppName("Streaming Tweet Analyzer")
    sc = SparkContext(conf=conf)
    # this will exit if arguments are not valid
    parseAndValidateArguments(sys.argv)

    ssc = StreamingContext(sc, 5)

    ssc.checkpoint(checkpointDir)

    # set up the receiving Kafka stream
    print("Starting Kafka direct stream to broker list %s, input topic %s, output topic %s" % (brokerList, logsTopic, statsTopic))

    kafkaReceiverParams = {"metadata.broker.list": brokerList}
    kafkaStream = KafkaUtils.createDirectStream(ssc, [logsTopic], kafkaReceiverParams)

    # Create Dstrean from infile
    #kafkaReceiverParams = {"metadata.broker.list": brokerList}
    #kafkaStream = KafkaUtils.createDirectStream(ssc, [logsTopic], kafkaReceiverParams)
    #filestream = ssc.textFileStream("/home/jeya/Desktop/jeya/Python/python_exercise/case-study/infile")
    # filestream.pprint()

    zerotime = datetime.fromtimestamp(0)

    def parseLine(line):
        tweet = json.loads(line[1])
        try:
            return [{"sessId": tweet["id"], "text": tweet["text"]}]
        except Exception as err:
            print("Wrong line format (%s): " % line)
            return []

    #logsStream = filestream.flatMap(parseLine)
    logsStream = kafkaStream.flatMap(parseLine)
    logsStream.pprint()

    # returns a DStream with single-element RDDs containing only the total count
    sessionCount = logsStream.count()
    sessionCount.pprint()

    # data key types for the output map
    SESSION_COUNT = "SESS"
    MY_TWEETS = "TWEET"

    finalSessionCount = sessionCount.map(lambda c: ((long((datetime.now() - zerotime).total_seconds()) * 1000), {SESSION_COUNT: c}))
    finalSessionCount.pprint()

    import sys
    reload(sys)
    sys.setdefaultencoding('utf8')

    # Text per second
    textPerSecond = logsStream.map(lambda t: ((long((datetime.now() - zerotime).total_seconds()) * 1000), {MY_TWEETS: t['text'].encode("utf8")}))
    textPerSecond.pprint()

    # all the streams are unioned and combined
    # finalStats = finalSessionCount.union(requests).union(errors).union(ads).reduceByKey(lambda m1, m2: dict(m1.items() + m2.items()))
    finalStats = finalSessionCount.union(textPerSecond).reduceByKey(lambda m1, m2: dict(m1.items() + m2.items()))
    finalStats.pprint()

    def sendMetrics(itr):
        global brokerList
        prod = KafkaProducerWrapper.getProducer([brokerList])
        for m in itr:
            mstr = ",".join([str(x) + "->" + str(m[1][x]) for x in m[1]])
            prod.send(statsTopic, key=str(m[0]), value=str(m[0]) + ":(" + mstr + ")")
        prod.flush()

    # Each partitions uses its own Kafka producer (one per partition) to send the formatted message
    finalStats.foreachRDD(lambda rdd: rdd.foreachPartition(sendMetrics))

    print("Starting the streaming context... Kill me with ^C")

    ssc.start()
    ssc.awaitTermination()
