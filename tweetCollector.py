import tweepy
from tweepy import Stream
from tweepy.streaming import StreamListener
from tweepy import OAuthHandler

from pyspark.streaming import StreamingContext
from pyspark.streaming.kafka import KafkaUtils
from kafka import KafkaProducer
from kafka.errors import KafkaError


class KafkaProducerWrapper(object):
    producer = None

    @staticmethod
    def getProducer(brokerList):
        if KafkaProducerWrapper.producer == None:
            KafkaProducerWrapper.producer = KafkaProducer(
                bootstrap_servers=brokerList, value_serializer=str.encode)
        return KafkaProducerWrapper.producer


consumer_key = '#'
consumer_secret = '#'
access_token = '#'
access_secret = '#'

auth = OAuthHandler(consumer_key, consumer_secret)
auth.set_access_token(access_token, access_secret)

api = tweepy.API(auth)
prod = KafkaProducerWrapper.getProducer(["localhost:9092"])


class MyListener(StreamListener):

    def on_data(self, data):
        try:
            prod.send("mytweets", value=data)
            return True
        except BaseException as e:
            print("Error on_data: %s" % str(e))
        return True

    def on_error(self, status):
        print(status)
        return True


twitter_stream = Stream(auth, MyListener())
#twitter_stream.filter(follow=['288194904', '225012752'])
twitter_stream.filter(track=['#stocks'])
