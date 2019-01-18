import asyncio
import aiohttp
import json
import dateutil.parser
import time
import sys
sys.path.append('./src/')
from FWLiveParams import FWLiveParams

async def pollForex(symbols, authkey,accountid):
    i = 0
    while True:
        symbol = symbols[i % len(symbols)]
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                        url="https://api-fxpractice.oanda.com/v3/accounts/"+accountid+"/pricing",
                        headers={'Authorization': ('Bearer ' + authkey)},
                        params='instruments=' + symbol) as resp:
                    yield (await resp.json())
        except Exception as error:
            print("Error while fetching forex rates from Oanda: " + type(error).__name__ + " " + str(error.args))
            
        i += 1
        await asyncio.sleep(1)

async def forexPoller(symbols, authkey, accountid, orderbookAnalyser):
    async for ticker in pollForex(symbols=symbols, authkey=authkey,accountid=accountid):
        try:
            symbolBase = ticker['prices'][0]['instrument'].split("_")[0]
            symbolQuote = ticker['prices'][0]['instrument'].split("_")[1]
            asks = ticker['prices'][0]['asks']
            bids = ticker['prices'][0]['bids']
            payload = {}
            payload['exchange'] = "oanda"
            payload['symbol'] = symbolBase + "/" + symbolQuote
            payload['data'] = {}
            payload['data']['asks'] = [[float(asks[0]['price']),asks[0]['liquidity']]]
            payload['data']['bids'] = [[float(bids[0]['price']),bids[0]['liquidity']]]
            payload['timestamp'] = time.mktime(dateutil.parser.parse(ticker['time']).timetuple())
            print("Received " + symbolBase+"/"+ symbolQuote + " prices from Oanda")
        except Exception as error:
            print("Error interpreting Oanda ticker: " + type(error).__name__ + " " + str(error.args))

oandaCredentials=FWLiveParams.getOandaCredentials()
asyncio.ensure_future(
    forexPoller(
        symbols=['EUR_USD', 'GBP_USD'],
        authkey=oandaCredentials['apikey'],
        accountid=oandaCredentials['accountid'],
        orderbookAnalyser=None))
loop = asyncio.get_event_loop()      
loop.run_forever()