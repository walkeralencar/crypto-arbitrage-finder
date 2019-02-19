from typing import List
from mock import patch, Mock
import pytest

from FWLiveParams import FWLiveParams
from OrderbookAnalyser import OrderbookAnalyser
from OrderRequest import OrderRequest, OrderRequestStatus, OrderRequestType

from threading import Condition, Thread
import time
from FeeStore import FeeStore
from TradingStrategy import TradingStrategy
from Trader import Trader
from InitLogger import logger
import asyncio

#vol_BTC=[1,0.1,0.01]
vol_BTC = [1]


def getOrderbookAnalyser():
    parameters = FWLiveParams()
    parameters.output = FWLiveParams.output_kafkaaws
    return OrderbookAnalyser(
        vol_BTC=vol_BTC,
        edgeTTL=30,
        priceTTL=60,
        resultsdir='./results/',
        priceSource=OrderbookAnalyser.PRICE_SOURCE_CMC,
        trader=Trader(is_sandbox_mode=True),
#        neo4j_mode=FWLiveParams.neo4j_mode_localhost,
#        dealfinder_mode=FWLiveParams.dealfinder_mode_neo4j,
        neo4j_mode=FWLiveParams.neo4j_mode_disabled,
        dealfinder_mode=FWLiveParams.dealfinder_mode_networkx,
        kafkaCredentials=parameters.getKafkaProducerCredentials())


@pytest.fixture(scope="class")
def getCMCSampleFetch():
    ticker = {}

    ticker['BTC/USD'] = {'symbol': 'BTC/USD', 'timestamp': 100*1000, 'last': 9000}

    ticker['ETH/USD'] = {'symbol': 'ETH/USD', 'timestamp': 100*1000, 'last': 100}

    ticker['ETH/BTC'] = {'symbol': 'ETH/BTC', 'timestamp': 100*1000, 'last': 0.03}

    return ticker


class TestClass(object):

    def test_threeNodesNoFees(self,monkeypatch, mocker):
        feeRates = [0]#[0.02]
        for feeRate in feeRates:
            def getTakerFeeMock(self,exchangename, symbol):
                    return feeRate
            monkeypatch.setattr(FeeStore, 'getTakerFee', getTakerFeeMock)
            
            orderbookAnalyser = getOrderbookAnalyser()
            cmc = getCMCSampleFetch()
            if orderbookAnalyser.neo4j_mode != FWLiveParams.neo4j_mode_disabled:
                orderbookAnalyser.arbitrageGraphNeo.graphDB.resetDBData()
            
            mocker.spy(orderbookAnalyser.trader, 'execute')

            orderbookAnalyser.updateCoinmarketcapPrice(cmc)
            orderbookAnalyser.update(
                'kraken',
                'BTC/USD',
                bids=[[9000, 1]],
                asks=[[10000, 1]],
                timestamp=100)
            orderbookAnalyser.update(
                'kraken',
                'ETH/USD',
                bids=[[100, 1000]],
                asks=[[200, 1000]],
                timestamp=101)
            orderbookAnalyser.update(
                'kraken',
                'ETH/BTC',
                bids=[[0.03, 1000]],
                asks=[[0.04, 1000]],
                timestamp=102)

            assert orderbookAnalyser.trader.execute.call_count == len(vol_BTC)
            orderRequestLists = orderbookAnalyser.trader.execute.call_args_list[0][0][0].getOrderRequestLists()
            
            orderRequestList = orderRequestLists[0][1]
            assert (orderRequestList.market, orderRequestList.amount, orderRequestList.price, orderRequestList.type,orderRequestList.getStatus()) == \
                    ('BTC/USD', vol_BTC[0], 9000, OrderRequestType.SELL,OrderRequestStatus.INITIAL)

            orderRequestList = orderRequestLists[0][2]
            assert (orderRequestList.market, orderRequestList.amount, orderRequestList.price, orderRequestList.type,orderRequestList.getStatus()) == \
                    ('ETH/USD',vol_BTC[0] / cmc['ETH/BTC']['last'], 200,OrderRequestType.BUY, OrderRequestStatus.INITIAL)

            orderRequestList = orderRequestLists[0][0]
            assert (orderRequestList.market, orderRequestList.amount, orderRequestList.price, orderRequestList.type,orderRequestList.getStatus()) == \
                    ('ETH/BTC',vol_BTC[0] / cmc['ETH/BTC']['last'], 0.03,OrderRequestType.SELL, OrderRequestStatus.INITIAL)

    def test_threeNodesWithFees(self,monkeypatch, mocker):
        feeRates = [0.0951]
        for feeRate in feeRates:
            def getTakerFeeMock(self,exchangename, symbol):
                    return feeRate
            monkeypatch.setattr(FeeStore, 'getTakerFee', getTakerFeeMock)
            monkeypatch.setattr(TradingStrategy,'MIN_PROFIT_LIMIT_PERCENTAGE',0)
            orderbookAnalyser = getOrderbookAnalyser()
            cmc = getCMCSampleFetch()
            if orderbookAnalyser.neo4j_mode != FWLiveParams.neo4j_mode_disabled:
                orderbookAnalyser.arbitrageGraphNeo.graphDB.resetDBData()
            
            mocker.spy(orderbookAnalyser.trader, 'execute')
            mocker.spy(orderbookAnalyser.kafkaProducer, 'sendAsync')
            orderbookAnalyser.updateCoinmarketcapPrice(cmc)
            orderbookAnalyser.update(
                'kraken',
                'BTC/USD',
                bids=[[9000, 1]],
                asks=[[10000, 1]],
                timestamp=100)
            orderbookAnalyser.update(
                'kraken',
                'ETH/USD',
                bids=[[100, 1000]],
                asks=[[200, 1000]],
                timestamp=101)
            orderbookAnalyser.update(
                'kraken',
                'ETH/BTC',
                bids=[[0.03, 1000]],
                asks=[[0.04, 1000]],
                timestamp=102)

            # wait for the Deal finder Threads to run
            asyncio.get_event_loop().run_until_complete(asyncio.sleep(1))
            time.sleep(2)
            #time.sleep(10)
            assert orderbookAnalyser.trader.execute.call_count == len(vol_BTC)
            assert orderbookAnalyser.kafkaProducer.sendAsync.call_count == len(vol_BTC)
            orderRequestLists = orderbookAnalyser.trader.execute.call_args_list[0][0][0].getOrderRequestLists()
            
            orderRequestList = orderRequestLists[0][0]
            assert (orderRequestList.market, orderRequestList.amount, orderRequestList.price, orderRequestList.type,orderRequestList.getStatus()) == \
                    ('BTC/USD', vol_BTC[0], 9000, OrderRequestType.SELL,OrderRequestStatus.INITIAL)

            orderRequestList = orderRequestLists[0][1]
            assert (orderRequestList.market, orderRequestList.amount, orderRequestList.price, orderRequestList.type,orderRequestList.getStatus()) == \
                    ('ETH/USD', vol_BTC[0] / cmc['ETH/BTC']['last'], 200,OrderRequestType.BUY, OrderRequestStatus.INITIAL)

            orderRequestList = orderRequestLists[0][2]
            assert (orderRequestList.market, orderRequestList.amount, orderRequestList.price, orderRequestList.type,orderRequestList.getStatus()) == \
                    ('ETH/BTC', vol_BTC[0] / cmc['ETH/BTC']['last'], 0.03,OrderRequestType.SELL, OrderRequestStatus.INITIAL)

            orderbookAnalyser.terminate()
    def test_threeNodesWithTooHighFees(self,monkeypatch, mocker):
        feeRates = [0.0952]
        for feeRate in feeRates:
            def getTakerFeeMock(self,exchangename, symbol):
                    return feeRate
            monkeypatch.setattr(FeeStore, 'getTakerFee', getTakerFeeMock)
            monkeypatch.setattr(TradingStrategy,'MIN_PROFIT_LIMIT_PERCENTAGE',0)
            orderbookAnalyser = getOrderbookAnalyser()
            cmc = getCMCSampleFetch()

            if orderbookAnalyser.neo4j_mode != FWLiveParams.neo4j_mode_disabled:
                orderbookAnalyser.arbitrageGraphNeo.graphDB.resetDBData()
            
            mocker.spy(orderbookAnalyser.trader, 'execute')

            orderbookAnalyser.updateCoinmarketcapPrice(cmc)
            orderbookAnalyser.update(
                'kraken',
                'BTC/USD',
                bids=[[9000, 1]],
                asks=[[10000, 1]],
                timestamp=100)
            orderbookAnalyser.update(
                'kraken',
                'ETH/USD',
                bids=[[100, 1000]],
                asks=[[200, 1000]],
                timestamp=101)
            orderbookAnalyser.update(
                'kraken',
                'ETH/BTC',
                bids=[[0.03, 1000]],
                asks=[[0.04, 1000]],
                timestamp=102)

            assert orderbookAnalyser.trader.execute.call_count == 0

    def test_crossExchangeAsync(self,monkeypatch, mocker):
        async def asyncWrapper(monkeypatch, mocker):            
            self.test_crossExchange(monkeypatch, mocker)

        def stop_loop():
            time.sleep(3)
            loop.call_soon_threadsafe(loop.stop)

        loop = asyncio.get_event_loop()      
        asyncio.ensure_future(asyncWrapper(monkeypatch, mocker))
        Thread(target=stop_loop).start()
        loop.run_forever()


    def test_crossExchange(self,monkeypatch, mocker):
        feeRates = [0]#[0.02]
        for feeRate in feeRates:
            def getTakerFeeMock(self,exchangename, symbol):
                    return feeRate
            monkeypatch.setattr(FeeStore, 'getTakerFee', getTakerFeeMock)
            
            orderbookAnalyser = getOrderbookAnalyser()
            cmc = getCMCSampleFetch()

            if orderbookAnalyser.neo4j_mode != FWLiveParams.neo4j_mode_disabled:
                orderbookAnalyser.arbitrageGraphNeo.graphDB.resetDBData()
            
            mocker.spy(orderbookAnalyser.trader, 'execute')

            orderbookAnalyser.updateCoinmarketcapPrice(cmc)
            orderbookAnalyser.update(
                'kraken',
                'BTC/USD',
                bids=[[9000, 1]],
                asks=[[10000, 1]],
                timestamp=100)
            orderbookAnalyser.update(
                'kraken',
                'ETH/USD',
                bids=[[100, 1000]],
                asks=[[200, 1000]],
                timestamp=101)
            orderbookAnalyser.update(
                'binance',
                'ETH/BTC',
                bids=[[0.03, 1000]],
                asks=[[0.04, 1000]],
                timestamp=102)


            assert orderbookAnalyser.trader.execute.call_count == len(vol_BTC)
            orderRequestLists = orderbookAnalyser.trader.execute.call_args_list[0][0][0].getOrderRequestLists()
            
            orderRequestList = orderRequestLists[1].getOrderRequests()[0]
            assert (orderRequestList.market, orderRequestList.amount, orderRequestList.price, orderRequestList.type,orderRequestList.getStatus()) == \
                    ('BTC/USD', vol_BTC[0], 9000, OrderRequestType.SELL,OrderRequestStatus.INITIAL)

            orderRequestList = orderRequestLists[1].getOrderRequests()[1]
            assert (orderRequestList.market, orderRequestList.amount, orderRequestList.price, orderRequestList.type,orderRequestList.getStatus()) == \
                    ('ETH/USD',vol_BTC[0] / cmc['ETH/BTC']['last'], 200,OrderRequestType.BUY, OrderRequestStatus.INITIAL)

            orderRequestList = orderRequestLists[0].getOrderRequests()[0]
            assert (orderRequestList.market, orderRequestList.amount, orderRequestList.price, orderRequestList.type,orderRequestList.getStatus()) == \
                    ('ETH/BTC',vol_BTC[0] / cmc['ETH/BTC']['last'], 0.03,OrderRequestType.SELL, OrderRequestStatus.INITIAL)