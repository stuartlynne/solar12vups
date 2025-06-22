
import sys

import traceback
from enum import Enum
import tabulate

import logging
from lib.log import setup_logger, xreport
logger = logging.getLogger(__name__)



class PowerState (Enum):
    noPV_noBattery = 0        # No PV, no Battery, no Load           pvps_v==0 and load_a==0
    noPV_noCharging_noLoad = 1   # No PV, Battery no Load                pvps v==0 and load_a==0               
    PV_Charging_noLoad = 2     # PV charging Battery, no Load          pvps_v!=0 

    noPV_Discharging_Load = 3      # No PV, Battery powering load          pvps_v==0 and load_a>0
    PV_Charging_Load = 4        # PV charging Battery and powering Load pvps_v!=0 and pvps_a<=load_a
    PV_Split_Load = 5           # PV and Battery are powering Load      pvps_v!=0 and load_a!=0 pvps_a==load_a
    UNKNOWN = 6 

PowerStateHelp = {
       PowerState.noPV_noBattery:          ("No PV/PS ", "Battery",            "Load off", "pvps_v==0 and load_a==0",),
       PowerState.noPV_noCharging_noLoad:  ("No PV,/PS", "Battery",            "Load off", "pvps v==0 and load_a==0 ",),              
       PowerState.PV_Charging_noLoad:      ("PV/PS on ", "Battery charging",   "Load off",  "pvps_v != 0 ",),

       PowerState.noPV_Discharging_Load:    ("No PV/PS ", "Battery discharging","Load on",  "pvps_v == 0 and load_a > 0",),
       PowerState.PV_Charging_Load:        ("PV/PS on ", "Battery charging",   "Load on",  "pvps_v != 0 and pvps_a >= load_a",),
       PowerState.PV_Split_Load:           ("PV/PS on ", "Battery discharging","Load on",  "pvps_v != 0 and load_a != 0 pvps_a < load_a",),

       PowerState.UNKNOWN:                 ("PV/PS n/a", "Battery n/a",        "Load n/a", "pvps_v != 0 and load_a != 0 pvps_a == load_a",),
}

class LiFePo4:
    # https://www.vatrerpower.com/blogs/news/lifepo4-voltage-chart-a-comprehensive-guide
    DischargeTable1 = {
            100: 14.6,
            90: 13.4,
            80: 13.28,
            70: 13.2,
            60: 13.08,
            50: 13.04,
            40: 13.0,
            30: 12.88,
            20: 12.8,
            10: 12.0,
            0: 10.0,
    }
    # https://www.renogy.com/blog/lifepo4-voltage-chart
    DischargeTable2 = {
            #100: 14.6, # 100% charging
            100: 13.6, # 100% reset
            90: 13.4,
            80: 13.3,
            70: 13.2,
            60: 13.1,
            50: 13.0,
            40: 13.0,
            30: 12.9,
            20: 12.8,
            10: 12.0,
            0: 10.0,
    }
    # https://blog.ecoflow.com/us/lifepo4-voltage-chart/
    DischargeTable = {
            "100% Charging": 14.6, # 100% charging
            "100% Rest": 13.6, # 100% reset
            #"90%": 13.4,
            #"80%": 13.3,
            #"70%": 13.2,
            #"60%": 13.1,
            "50%": 13.0,
            #"40%": 12.9,
            #"30%": 12.8,
            "20%": 12.5,
            "10%": 12.0,
            "5%":  11.6,
            "0%":  11.0,
            #"0%":  10.0,
    }

    def estPercent(voltage):
        # Voltage-to-percentage table (reverse of DischargeTableFull)
        discharge_points = [
            (13.6, 100),
            (13.4, 90),
            (13.3, 80),
            (13.2, 70),
            (13.1, 60),
            (13.0, 50),
            (12.9, 40),
            (12.8, 30),
            (12.5, 20),
            (12.0, 10),
            (11.0, 0)
        ]

        # If voltage is out of bounds
        if voltage >= discharge_points[0][0]:
            return 100
        if voltage <= discharge_points[-1][0]:
            return 0

        # Piecewise linear interpolation
        for i in range(len(discharge_points) - 1):
            v_high, p_high = discharge_points[i]
            v_low, p_low = discharge_points[i + 1]

            if v_low <= voltage <= v_high:
                # Linear interpolation formula
                return p_low + (p_high - p_low) * ((voltage - v_low) / (v_high - v_low))

        # Fallback
        return 0

    def estRuntime(soc_percent, battery_capacity=8, batteries=1, load_a=0):
        if load_a <= 0:
            return float('inf')  # Infinite runtime
        remaining_ah = (soc_percent / 100.0) * battery_capacity * batteries
        h = (remaining_ah / load_a)# * 60.0
        #logging.info(f"LiFePo4:estRuntime: {soc_percent:2.0f}% {battery_capacity}Ah {load_a:3.1f}A {h:.1f}hour")
        return h


class PVPS:
    def __init__(self,name=None): 
        self.reset()
    def reset(self,):
        self.set()
            
    def set (self, pvps_v=0, pvps_a=0, to_batt_w=None, to_load_w=None, ):
        self.pvps_v = pvps_v
        self.pvps_a = pvps_a
        self.pvps_w = pvps_v*pvps_a     # Total measured power from PVPS

        self.to_batt_w = to_batt_w            # Power to battery
        self.to_load_w = to_load_w            # Power to load

class Batt:
    def __init__(self,name=None): 
        self.reset()
    def reset(self,):
        self.set()
    def set(self, batt_v=0, from_pvps_w=None, to_load_w=None,):
        self.batt_v = batt_v
        self.from_pvps_w = from_pvps_w    # Power from PVPS to battery
        self.to_load_w = to_load_w    # Power from battery to load
        self.batt_w = (from_pvps_w if from_pvps_w else 0) + (to_load_w if to_load_w else 0)
        #self.batt_w = 

class Load:
    def __init__(self,name=None): 
        self.reset()
    def reset(self,):
        self.set()
    def set(self, load_v=0, load_a=0, from_pvps_w=None, ):
        self.load_v = load_v
        self.load_a = load_a
        self.load_w = load_v * load_a  # Total measured power to load

        # is all power coming from PVPS?
        if from_pvps_w and from_pvps_w > 0:
            if from_pvps_w > self.load_w*.98:
                self.from_pvps_w = self.load_w
                self.from_batt_w = None
                #self.from_batt_w = -(from_pvps_w - self.load_w)
                logging.info(f"Load:set: from_pvps_w={from_pvps_w} > load_w={self.load_w} setting from_pvps_w to load_w AAAA")
            else:
                # is it split between PVPS and battery?
                self.from_pvps_w = from_pvps_w
                self.from_batt_w = -(from_pvps_w - self.load_w)
                logging.info(f"Load:set: from_pvps_w={from_pvps_w} < load_w={self.load_w} setting from_batt_w to {self.from_batt_w} BBBB")
        # all power coming from battery
        else:
            self.from_pvps_w = None
            self.from_batt_w = self.load_w if self.load_v > 0 else None
            logging.info(f"Load:set: load_v={load_v} load_a={load_a} from_pvps_w={from_pvps_w} from_batt_w={self.from_batt_w} CCCC")


class Power:

    def __init__(self, name=None, ):

        self.name = name
        #self.battery_capacity = battery_capacity
        #self.batteries = batteries
        self.pvps = PVPS(name=name)
        self.batt = Batt(name=name)
        self.load = Load(name=name)
        self.info = None
        self.powerState = self.getPowerState() 

    def __str__(self):
        tl = []
        #          Type    Voltage (V)       Current (A)       Power (W)               PVPS->Batt(W)          PVPS->Load (W)         Batt->Load (W)
        tl.append(['LOAD', self.load.load_v, self.load.load_a, self.load.load_w, None, None,                  self.load.from_pvps_w, self.load.from_batt_w,])
        tl.append(['BATT', self.batt.batt_v, None,             None,             None, self.batt.from_pvps_w, None,                  self.batt.to_load_w,]), 
        tl.append(['PVPS', self.pvps.pvps_v, self.pvps.pvps_a, self.pvps.pvps_w, None, self.pvps.to_batt_w,   self.pvps.to_load_w,   None, ]),

        tl_table = tabulate.tabulate(tl, headers=[
            'Type', 
            'Voltage (V)', 'Current (A)', 'Power (W)', '', 
            'PVPS->Batt (W)', 
            'PVPS->Load (W)', 'Batt->LOAD (W)'], tablefmt='grid')

        return f"{self.name} {self.powerState.name}:\n{tl_table}"

    def _set(self, powerState):
        self.powerState = powerState
        logging.info(f"PowerGauge:_set: {self}")
        return powerState

    def getPowerState(self, pvps_v=0, pvps_a=0, load_v=0, load_a=0, batt_v=0, info=None):
        if info:
            logging.info(f"PowerGauge:getPowerState: {self.name} pvps_v={pvps_v} pvps_a={pvps_a} load_v={load_v} load_a={load_a} batt_v={batt_v} {info} AAAA ")
        #logging.info(f"PowerGauge:getPowerState: {data_history}")
        #load_status = data_history['load_status'][-1]
        #logging.info(f"PowerGauge:getPowerState: load_flag={load_flag} pvps_v={pvps_v} pvps_a={pvps_a} batt_v={batt_v} pvpa={pvps_a} load_a={load_a}")

        self.load_flag = load_v > 0 
        self.info = info
        pvps_w = pvps_v * pvps_a if pvps_v > 0 else 0
        load_w = load_v * load_a if load_v > 0 else 0

        if not self.load_flag:

            #0
            if pvps_v == 0 and batt_v == 0:
                self.batt.reset()
                self.pvps.reset()
                self.load.reset()
                return self._set(PowerState.noPV_noBattery)
            #1
            if pvps_v == 0 and batt_v > 0:
                self.batt.set(batt_v=batt_v,) 
                self.pvps.reset()
                self.load.reset()
                return self._set(PowerState.noPV_noCharging_noLoad)
            #2
            if pvps_v > 0:
                self.pvps.set(pvps_v=pvps_v, pvps_a=pvps_a, to_batt_w=pvps_w, )
                self.batt.set(batt_v=batt_v, from_pvps_w=pvps_w, )
                self.load.reset()
                return self._set(PowerState.PV_Charging_noLoad)

            return self._set(PowerState.UNKNOWN)

        #if load_status == 'on':
        if self.load_flag:
            # noPV_Dischargning = 3      # No PV, Battery powering load          pvps_v==0 and load_a>0
            # PV_Charging_Load = 4        # PV charging Battery and powering Load pvps_v!=0 and pvps_a<=load_a
            # PV_Split_Load = 5           # PV and Battery are powering Load      pvps_v!=0 and load_a!=0 pvps_a==load_a

            #3
            if pvps_v == 0 and load_a > 0:
                self.load.set(load_v=load_v, load_a=load_a, )
                self.batt.set(batt_v=batt_v, to_load_w=self.load.load_w, )
                self.pvps.reset()
                return self._set(PowerState.noPV_Discharging_Load)
            #4
            if pvps_v > 0 and pvps_w >= (load_w*.98):
                self.load.set(load_v=load_v, load_a=load_a, from_pvps_w=pvps_w) 
                self.batt.set(batt_v=batt_v, from_pvps_w=pvps_w-self.load.load_w, )
                self.pvps.set(pvps_v=pvps_v, pvps_a=pvps_a, to_load_w=self.load.load_w, to_batt_w=self.batt.from_pvps_w)

                #logging.info(f"PowerGauge:getPowerState: PV_Charging_Load pvps_v={pvps_v}  pvps_w={pvps_a} load_w={load_a}")
                return self._set(PowerState.PV_Charging_Load)
            #5
            #if pvps_v > 0 and load_a > 0 and pvps_a < (load_a*1.2):
            if pvps_v > 0 and load_a > 0 and pvps_w < (load_w*1.1):
                #logging.info(f"PowerGauge:getPowerState: PV_Split_Load pvps_v={pvps_v}  pvps_w={pvps_a} load_w={load_a}")

                self.load.set(load_v=load_v, load_a=load_a, from_pvps_w=pvps_w) 
                self.batt.set(batt_v=batt_v, to_load_w=self.load.from_batt_w,  )
                self.pvps.set(pvps_v=pvps_v, pvps_a=pvps_a, to_load_w=self.load.from_pvps_w, )

                return self._set(PowerState.PV_Split_Load)

            #logging.info(f"PowerGauge:getPowerState: UNKNOWN LOAD ON pvps_v={pvps_v} batt_v={batt_v} pvps_a={pvps_a} load_a={load_a}")
            return self._set(PowerState.UNKNOWN)

        #logging.info(f"PowerGauge:getPowerState: UNKNOWN load_flag={self.load_flag} pvps_v={pvps_v} batt_v={batt_v} pvps_a={pvps_a} load_a={load_a}")

        return self._set(PowerState.UNKNOWN)



if __name__ == "__main__":
    setup_logger()
    #def getPowerState(self, pvps_v=0, pvps_a=0, load_v=0, load_a=0, batt_v=0,):
                #return self._set(PowerState.noPV_noCharging_noLoad)
                #return self._set(PowerState.PV_Charging_noLoad)
    tests = [
            {'pvps_v': 0, 'pvps_a': 0, 'load_v': 0, 'load_a':  0, 'batt_v': 14.6, 'info': 'noPV noLoad'},
            {'pvps_v': 16, 'pvps_a': 1, 'load_v': 0, 'load_a':  0, 'batt_v': 14.6, 'info': 'PV Charging noLoad'},

            {'pvps_v': 0, 'pvps_a': 0, 'load_v': 14.6, 'load_a':  .5, 'batt_v': 14.6, 'info': 'noPV Discharging Load'},
            {'pvps_v': 16, 'pvps_a': 1, 'load_v': 14.6, 'load_a':  .5, 'batt_v': 14.6, 'info': 'PV Charging Load'},
            {'pvps_v': 16, 'pvps_a': 1, 'load_v': 14.6, 'load_a': 1.9, 'batt_v': 14.6, 'info': 'PV Split Load'},
    ]
    try:
        power = Power(name="TestPower", )
        for test in tests:
            state = power.getPowerState(**test)
            #logging.info(f"Test: {test} => PowerState: {state}")
            #logging.info(f"Test: PowerState: {state.name}")
            #logging.info(f"Power: {power}")
            #print(tabulate.tabulate([[state.name, *PowerStateHelp[state]]], headers=["State", "PV/PS", "Battery", "Load", "Condition"]))
    except Exception as e:
        logging.exception(f"Exception in main: {e}")
        traceback.print_exc(file=sys.stdout)


