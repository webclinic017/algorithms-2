from cryptofeed.defines import TRADES, L2_BOOK, BID, ASK

import pandas as pd
import json

import time
import datetime

import threading
import schedule
import redis

from algos.altcoin.backtest import perform_backtests
from algos.altcoin.live_trader import liveTrading
from utils import print


r = redis.Redis(host='localhost', port=6379, db=0)

async def altcoin_book(feed, pair, book, timestamp, receipt_timestamp):
    if float(r.get('altcoin_enabled').decode()) == 1:
        bid = float(list(book[BID].keys())[-1])
        ask = float(list(book[ASK].keys())[0])

        r.set('{}_best_bid'.format(pair), bid)
        r.set('{}_best_ask'.format(pair), ask)

async def altcoin_trade(feed, pair, order_id, timestamp, receipt_timestamp, side, amount, price):
    pass

def get_positions():
    r = redis.Redis(host='localhost', port=6379, db=0)
    config = pd.read_csv('algos/altcoin/config.csv')
    details_df = pd.DataFrame()

    for idx, row in config.iterrows():
        asset = row['name']

        curr_detail = pd.Series()
        curr_detail['name'] = asset
        backtest = pd.read_csv("data/trades_{}.csv".format(asset))
        
        try:
            curr_detail['position'] = r.get('{}_current_pos'.format(asset)).decode()
        except:
            curr_detail['position'] = "NONE"

        try:
            curr_detail['entry'] = round(float(r.get('{}_avgEntryPrice'.format(asset)).decode()),2)
        except:
            curr_detail['entry'] = 0
        
        try:
            curr_detail['pos_size'] = float(r.get('{}_pos_size'.format(asset)).decode())
        except:
            curr_detail['pos_size'] = 0

        try:
            curr_detail['live_price'] = float(r.get('{}_best_ask'.format(asset)).decode())
        except:
            curr_detail['live_price'] = 0


        curr_detail['backtest_position'] = 'SHORT' if backtest.iloc[-1]['Type'] == 'SELL' else 'LONG'
        curr_detail['backtest_date'] = backtest.iloc[-1]['Date']
        curr_detail['entry_price'] = round(backtest.iloc[-1]['Price'], 2)
        curr_detail['to_trade'] = row['to_trade']
        curr_detail['live_lev'] = int(row['mult'])
        
        try:
            curr_detail['live_pnl'] = round(((curr_detail['live_price'] - curr_detail['entry'])/curr_detail['entry']) * 100 * curr_detail['live_lev'], 2)
        except:
            curr_detail['live_pnl'] = 0

        details_df = details_df.append(curr_detail, ignore_index=True)

    return details_df


def daily_tasks():
    print("Time: {}".format(datetime.datetime.utcnow()))
    perform_backtests()
    print("\n")

    config = pd.read_csv('algos/altcoin/config.csv')

    for pair in config['name']:
        lt = liveTrading(pair)
        lt.set_position()


    enabled = 1

    try:
        enabled = float(r.get('altcoin_enabled').decode())
    except:
        pass

    
    if enabled == 1:
        details_df = get_positions()
        
        details_df['target_pos'] = details_df['backtest_position'].replace("LONG", 1).replace("SHORT", -1).replace("NONE", 0)
        details_df['curr_pos'] = details_df['position'].replace("LONG", 1).replace("SHORT", -1).replace("NONE", 0)

        to_close = details_df[details_df['target_pos'] == 0]

        for idx, row in to_close.iterrows():
            if row['to_trade'] == 1:
                if row['curr_pos'] != 0:
                    lt = liveTrading(symbol=row['name'])
                    lt.fill_order('close', row['position'].lower())
        
        to_open = details_df[details_df['target_pos'] != 0]

        for idx, row in to_open.iterrows():
            if row['to_trade'] == 1:
                if row['target_pos'] == row['curr_pos']:
                    print("As required for {}".format(row['name']))
                    pass
                elif row['target_pos'] * row['curr_pos'] == -1:
                    print("Closing and opening for {}".format(row['name']))
                    lt = liveTrading(symbol=row['name'])
                    lt.fill_order('close', row['position'].lower())
                    lt.fill_order('open', row['backtest_position'].lower())
                else:
                    print("Opening for {}".format(row['name']))
                    lt = liveTrading(symbol=row['name'])
                    lt.fill_order('open', row['backtest_position'].lower())


        print("\n")

def start_schedlued():
    while True:
        schedule.run_pending()
        time.sleep(1)

def hourly_tasks():
    details_df = get_positions()
    for idx, row in details_df.iterrows():
        lt = liveTrading(row['name'])
        lt.set_position()

def alt_bot():
    perform_backtests()
    pairs = json.load(open('algos/vol_trend/pairs.json'))

    for pair in pairs:
        lt = liveTrading(pair)
        lt.set_position()

    schedule.every().day.at("00:01").do(daily_tasks)
    schedule.every().hour.do(hourly_tasks)

    schedule_thread = threading.Thread(target=start_schedlued)
    schedule_thread.start()