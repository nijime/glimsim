from random import random
from time import sleep
import threading
import statistics

# real time between sim loops
INTERVAL = 0.00

SIMRATE = 1

# game rate progression per loop
# higher values might result in wasted time between cds
GAMERATE = 0.01


BASEHASTE = 0
BASECRIT = 0.06
BASEMASTERY = 0.12
BASEVERS = 0

DHASTE = 0.00014706
DCRIT = 0.00013889
DMASTERY = 0.00020833
DVERS = 0.00011765

MASTERY_EFFECTIVENESS = 1
AVERAGECRITS = True


def percentChance(p):
    return p >= (1-random())

def clamp(n, a, b):
    if n < a:
        return a
    elif n > b:
        return b
    else:
        return n


class Spell:

    def __init__(self, amount, cd, castTime):
        self.name = None

        self.basecd = cd
        self.baseAmount = amount
        self.baseCastTime = castTime
        self.baseCritChance = clamp(BASECRIT, 0, 1)

        self.amount = self.baseAmount * (1 + BASEMASTERY*MASTERY_EFFECTIVENESS)
        self.cd = self.basecd / (1+BASEHASTE)
        self.castTime = self.baseCastTime / (1+BASEHASTE)

        self.critChance = clamp(self.baseCritChance, 0, 1)

        self.curcd = 0
        self.cdRate = 1
        self.iReduction = 0

        self.numhits = 1
        self.onGCD = True

        def default(context):
            if AVERAGECRITS:
                amt = self.amount * (1 + self.critChance)
            else:
                didCrit = random() <= self.critChance
                amt = self.amount * (1 + didCrit / 1)

            if isinstance(context, Player):
                player = context
                #print(f"Casted {self.name}")
            else:
                sim=context
                sim.heal(amt, self.name)

        self.onCast = default

    @classmethod
    def onCastAlways(cls, context):
        if isinstance(context, Player):
            player = context
        else:
            sim = context
            ineffableBuff = sim.player.buffTracker.ineffable
            sim.procTracker.tryProc(ineffableBuff, sim.combatTime)

    def event(self, fn):
        setattr(self, fn.__name__, fn)

    def canCast(self):
        return self.curcd == 0

    def cast(self):
        def onCast(context):
            self.onCast(context)
            Spell.onCastAlways(context)

        self.curcd = self.cd
        return onCast

    def subCD(self, r):
        self.curcd = clamp(self.curcd-(r*(1+self.iReduction)), 0, self.basecd)

    def updateFields(self, curStats):
        haste = curStats.get("hastePercent", 0)
        mastery = curStats.get("masteryPercent", 0)
        crit = curStats.get("critPercent", 0)
        healMult = curStats.get("healMult")

        self.iReduction = curStats.get("ineffableReduction")

        self.cd = (self.basecd / (1+haste))
        self.amount = self.baseAmount * (1 + mastery * MASTERY_EFFECTIVENESS) * healMult
        self.critChance = clamp(crit, 0, 1)


class GCD(Spell):
    def __init__(self):
        super().__init__(0, 1.5, 0)
        self.name = None

    def subCD(self, r):
        self.curcd = clamp(self.curcd-r, 0, self.basecd)

    def cast(self):
        self.curcd = self.cd
        return self.onCast


class HolyShock(Spell):
    def __init__(self, amount):
        super().__init__(amount, 9, 0)
        self.name = "Holy Shock"
        self.baseCritChance = BASECRIT + 0.3
        self.critChance = clamp(self.baseCritChance, 0, 1)

        self.numGlimmers = 0

        def onCast(context):
            if AVERAGECRITS:
                amt = self.amount * (1 + self.critChance)
            else:
                didCrit = random() <= self.critChance
                amt = self.amount * (1 + didCrit / 1)

            if isinstance(context, Player):
                player = context
                glimmerTracker = player.glimmerTracker
                self.numGlimmers = glimmerTracker.count()

                glimmerTracker.hs()

            else:
                # do sim stuff
                sim = context
                sim.heal(amt, self.name, beaconPercent=0.4, hits=self.numhits)

                def procGlimmers():
                    for g in range(self.numGlimmers):
                        sim.cast("Glimmer of Light")

                t = threading.Timer(0.0, procGlimmers)
                t.start()

        self.onCast = onCast

    def cast(self):
        def onCast(context):
            self.onCast(context)
            Spell.onCastAlways(context)

        # divine purpose chance
        if percentChance(0.2):
            self.curcd = 0
            #print("### Holy Shock DP")
        else:
            self.curcd = self.cd

        return onCast

    def updateFields(self, curStats):
        haste = curStats.get("hastePercent", 0)
        mastery = curStats.get("masteryPercent", 0)
        crit = curStats.get("critPercent", 0)
        wingsActive = curStats.get("buffTracker").isActive("Avenging Wrath")
        healMult = curStats.get("healMult")
        hsMod = curStats.get("holyShockMod")

        self.iReduction = curStats.get("ineffableReduction")

        self.cd = ((self.basecd / (1+haste)) / (1 + int(wingsActive)))
        self.amount = self.baseAmount * (1 + mastery * MASTERY_EFFECTIVENESS) * healMult * hsMod
        self.critChance = clamp(crit + 0.3, 0, 1)


class GlimmerProc(Spell):
    def __init__(self, amount):
        super().__init__(amount, 0, 0)
        self.name = "Glimmer of Light"

        self.onGCD = False

        def onCast(context):
            if AVERAGECRITS:
                amt = self.amount * (1 + self.critChance)
            else:
                didCrit = random() <= self.critChance
                amt = self.amount * (1 + didCrit / 1)

            if isinstance(context, Player):
                player=context
            else:
                sim = context
                sim.heal(amt, self.name, beaconPercent=0.2)

        self.onCast = onCast

    def updateFields(self, curStats):
        haste = curStats.get("hastePercent", 0)
        mastery = curStats.get("masteryPercent", 0)
        crit = curStats.get("critPercent", 0)
        healMult = curStats.get("healMult")
        ineffable = curStats.get("ineffablePercent", 0)

        self.cd = (self.basecd / (1+haste)) / (1 + ineffable)
        self.amount = self.baseAmount * (1 + mastery * MASTERY_EFFECTIVENESS) * healMult * 1.4238
        self.critChance = clamp(crit, 0, 1)


class LightOfDawn(Spell):
    def __init__(self, amount, numhits):
        super().__init__(amount, 12, 0)
        self.name = "Light of Dawn"

        self.numhits = numhits

        def onCast(context):
            if AVERAGECRITS:
                amt = self.amount * self.numhits * (1 + self.critChance)
            else:
                numCrits = (random() * self.critChance * 5) % self.critChance
                amt = self.amount * self.numhits * (1 + numCrits / 5)

            if isinstance(context, Player):
                player = context
            else:
                # do sim stuff
                sim = context
                sim.heal(amt, self.name, beaconPercent=0.2, hits=self.numhits)


    def cast(self):
        def onCast(context):
            self.onCast(context)
            Spell.onCastAlways(context)

        # divine purpose chance
        if percentChance(0.2):
            self.curcd = 0
            #print("### Light of Dawn DP")
        else:
            self.curcd = self.cd

        return onCast


class CrusaderStrike(Spell):
    def __init__(self, hs, lod):
        super().__init__(0, 6, 0)
        self.name = "Crusader Strike"

        self.charges = 2

        self.hs = hs
        self.lod = lod

        def onCast(context):
            self.hs.subCD(1.5)
            self.lod.subCD(1.5)

            if isinstance(context, Player):
                pass
            else:
                sim = context
                #sim.heal(self.amount, self.name)

        self.onCast = onCast

    def canCast(self):
        return self.charges > 0

    def subCD(self, r):
        self.curcd = clamp(self.curcd-(r*(1+self.iReduction)), 0, 10)
        if self.curcd == 0 and self.charges < 2:
            self.charges = clamp(self.charges + 1, 0, 2)
            if self.charges < 2:
                self.curcd = self.cd


    def cast(self):
        def onCast(context):
            self.onCast(context)
            Spell.onCastAlways(context)

        if self.charges == 2:
            self.curcd = self.cd

        self.charges = self.charges - 1

        return onCast


class GlimmerInstance:
    def __init__(self, amount):
        self.baseAmount = amount
        self.baseCritChance = clamp(BASECRIT, 0, 1)

        self.amount = self.baseAmount * (1 + BASEMASTERY*MASTERY_EFFECTIVENESS)
        self.duration = 30

        self.critChance = clamp(self.baseCritChance, 0, 1)

    def subDuration(self, n):
        self.duration = clamp(self.duration - n, 0, 30)
    """
    def proc(self):
        if AVERAGECRITS:
            return self.amount * (1 + self.critChance)
        else:
            didCrit = random() <= self.critChance

            return self.amount * (1 + didCrit / 1)
    """


class GlimmerTracker:
    def __init__(self, amount):
        self.amount = amount
        self.glimmers = []

    def count(self):
        return len(self.glimmers)

    def hs(self):
        amt = []
        #for glimmer in self.glimmers:
        #    amt.append(glimmer.proc())

        self.glimmers.append(GlimmerInstance(self.amount))
        if len(self.glimmers) > 8:
            del self.glimmers[0]

        return amt

    def subDuration(self, n):
        for glimmer in self.glimmers:
            glimmer.subDuration(n)
            if glimmer.duration == 0:
                self.glimmers.remove(glimmer)
    """
    def updateFields(self, curStats):
        for instance in self.glimmers:
            instance.updateFields(curStats)
    """


class FlashOfLight(Spell):
    def __init__(self, amount):
        super().__init__(amount, 0, 1.5)


class HolyLight(Spell):
    def __init__(self, amount):
        super().__init__(amount, 0, 3)


class AvengingWrath(Spell):
    def __init__(self, lightsDecree, numAvengersMight):
        super().__init__(0, 90, 0)
        self.name = "Avenging Wrath"

        #self.cd = self.basecd

        self.avengingWrathBuff = AvengingWrathBuff(lightsDecree, numAvengersMight)

        def onCast(context):
            if isinstance(context, Player):
                player = context
                player.buffTracker.apply(self.avengingWrathBuff)
                return

            player = context.player
            onCast(player)
            #print("oncast")

        self.onCast = onCast

    def cast(self):
        def onCast(context):
            self.onCast(context)
            Spell.onCastAlways(context)

        self.curcd = self.cd
        return onCast

    def updateFields(self, curStats):
        pass


class HolyAvenger(Spell):
    def __init__(self):
        super().__init__(0, 90, 0)
        self.name = "Holy Avenger"

        #self.cd = self.basecd

        self.holyAvengerBuff = HolyAvengerBuff()

        def onCast(context):
            if isinstance(context, Player):
                player = context
                player.buffTracker.apply(self.holyAvengerBuff)
                return

            player = context.player
            onCast(player)
            #print("oncast")

        self.onCast = onCast

    def cast(self):
        def onCast(context):
            self.onCast(context)
            Spell.onCastAlways(context)

        self.curcd = self.cd
        return onCast

    def updateFields(self, curStats):
        pass


class Buff:
    def __init__(self, startDuration, maxDuration, maxStacks):
        self.maxDuration = maxDuration
        self.startDuration = startDuration
        self.maxStacks = maxStacks

        self.duration = 0
        self.stacks = 0

        #self.refreshOnStack = True

        def whileActive(player):
            pass

        self.whileActive = whileActive

    def addStacks(self, n):
        self.duration = self.maxDuration
        self.stacks += clamp(n, 0, self.maxStacks)

    def apply(self):
        self.duration = self.startDuration
        self.stacks = 1

    def subDuration(self, n):
        self.duration = clamp(self.duration - n, 0, self.maxDuration)


class AvengingWrathBuff(Buff):
    def __init__(self, lightsDecree, numAvengersMight):
        super().__init__( (1 + 0.2*lightsDecree) * 25, 100, 1)
        self.name = "Avenging Wrath"

        self.lightsDecree = lightsDecree
        self.numAvengersMights = numAvengersMight

        def whileActive(player):
            @player.statMod(1)
            def AW():
                # add crit rating equivalent to 20% crit
                player.curStats["critRating"] += 20 / (DCRIT*100)
                player.curStats["masteryRating"] += 863 * self.numAvengersMights
                player.curStats["healMult"] *= 1.3

        self.whileActive = whileActive

    def visionProc(self):
        self.duration = clamp(self.duration + (1 + 0.2*self.lightsDecree) * 5, 0, self.maxDuration)
        self.stacks = 1


class HolyAvengerBuff(Buff):
    def __init__(self):
        super().__init__( 20, 100, 1)
        self.name = "Holy Avenger"

        def whileActive(player):
            @player.statMod(1)
            def HA():
                # add haste rating equivalent to 30% haste
                player.curStats["hasteRating"] += 30 / (DHASTE*100)
                player.curStats["holyShockMod"] *= 1.3

        self.whileActive = whileActive


class IneffableTruth(Buff):
    def __init__(self, reduction):
        super().__init__( 10, 10, 1)
        self.name = "Ineffable Truth"

        self.ppm = 1

        self.reduction = reduction
        def whileActive(player):
            @player.statMod(1)
            def HA():
                player.curStats["ineffableReduction"] = self.reduction

        self.whileActive = whileActive


class AvengingWrathCrit(Buff):
    def __init__(self, holyShock):
        super().__init__(30, 30, 1)
        self.holyShock = holyShock


class PPMTracker:
    def __init__(self, player):
        self.player = player
        self.procs = {}
        self.luckProtection = {}
        self.lastProc = {}
        self.lastProcAttempt = {}

    def tryProc(self, buff, combatTime):
        name = buff.name
        if not self.procs.get(buff.name):
            self.procs[name] = buff
            self.lastProc[name] = 0
            self.lastProcAttempt[name] = 0
            self.luckProtection[name] = max(1, 1 + 3 * (0 * buff.ppm / 60.0 - 1.5))
        else:
            tLastProc = combatTime - self.lastProc.get(name)
            tLastProcAttempt = combatTime - self.lastProcAttempt.get(name)

            self.lastProcAttempt[name] = combatTime

            procChance = self.luckProtection.get(name) * (buff.ppm / 60) * min(tLastProcAttempt, 10)
            self.luckProtection[name] = max(1, 1 + 3 * (tLastProc * buff.ppm / 60.0 - 1.5))

            #print(procChance)
            if percentChance(procChance):
                #print(procChance)
                self.lastProc[name] = combatTime
                #print("PROC", name)
                self.player.buffTracker.apply(buff)


class BuffTracker:
    def __init__(self):
        self.ineffable = IneffableTruth(0)
        self.buffs = {}

    def getBuffList(self):
        return list(self.buffs.keys())

    def subDuration(self, n):
        toDelete = []
        for name, buff in self.buffs.items():
            buff.subDuration(n)
            if buff.duration == 0:
                buff.stacks = 0
                toDelete.append(buff.name)

        for key in toDelete:
            self.buffs.pop(key)

    def apply(self, buff):
        if not self.buffs.get(buff.name):
            self.buffs[buff.name] = buff

        self.buffs[buff.name].apply()

    def isActive(self, name):
        return not (self.buffs.get(name) is None)


def valTotal(d):
    toRet = 0

    for k, v in d.items():
        toRet += v

    return toRet


def sortKeys(d):
    return sorted(d.keys(), key = lambda x : d.get(x), reverse=True)


class SpellTracker:
    def __init__(self):
        self.gcd = GCD()
        self.spells = {}

    def registerSpell(self, spell):
        if not self.spells.get(spell.name):
            self.spells[spell.name] = spell
        else:
            print(f"{spell.name} is already registered")

    def canCast(self, spellName=None):
        if not spellName:
            return self.gcd.canCast()

        if not self.spells.get(spellName):
            print(f"Spell {spellName} is not a registered spell")
            return 0

        return self.spells.get(spellName).canCast()

    def cast(self, spellName):
        if not self.spells.get(spellName):
            print(f"Spell {spellName} is not a registered spell")
            return None

        spell = self.spells.get(spellName)
        onGCD = spell.onGCD
        ret = None

        if (not onGCD or self.canCast()) and self.canCast(spellName):
            ret = spell.cast()
            if onGCD:
                self.gcd.cast()

        return ret

    def subCD(self, n):
        self.gcd.subCD(n)
        for _, spell in self.spells.items():
            spell.subCD(n)

    def updateFields(self, curStats):
        for _, spell in self.spells.items():
            spell.updateFields(curStats)


class Player:
    def __init__(self, hasteRating, masteryRating, critRating, versRating, azeritePowers, **kwargs):
        assert isinstance(azeritePowers, dict)

        self.baseStats = {"hasteRating": hasteRating,
                          "masteryRating": masteryRating,
                          "critRating": critRating,
                          "versRating": versRating,
                          "holyShockMod": 1,
                          "ineffableReduction": 0
                          }

        self.curStats = self.baseStats.copy()
        self.baseStats["healMult"] = 1 * (1 + self.getVers())
        self.curStats = self.baseStats.copy()

        self.azeritePowers = azeritePowers

        lightsDecree = azeritePowers.get("Light's Decree", 0)
        numAvengersMight = azeritePowers.get("Avenger's Might", 0)

        self.lastBuffList = None
        self.buffTracker = BuffTracker()
        self.buffTracker.ineffable = IneffableTruth(kwargs.get("ineffableReduction"))

        self.spellTracker = SpellTracker()
        self.spellTracker.registerSpell(HolyShock(29199))
        self.spellTracker.registerSpell(LightOfDawn(12106, 5))

        hs = self.spellTracker.spells.get("Holy Shock")
        lod = self.spellTracker.spells.get("Light of Dawn")
        self.spellTracker.registerSpell(CrusaderStrike(hs, lod))

        self.spellTracker.registerSpell(HolyAvenger())
        self.spellTracker.registerSpell(AvengingWrath(lightsDecree, numAvengersMight))

        self.glimmerTracker = GlimmerTracker(2505+2180+2392)
        self.spellTracker.registerSpell(GlimmerProc(self.glimmerTracker.amount))

        self.batchedMods = {}

    def getSpellCD(self, spellName):
        spell = self.spellTracker.spells.get(spellName)

        if not spell:
            print("Invalid spell name")
        else:
            return spell.curcd

    def getSpellMaxCD(self, spellName):
        if spellName.lower() == "gcd":
            return self.spellTracker.gcd.cd
        else:
            spell = self.spellTracker.spells.get(spellName)
            if not spell:
                print("Invalid spell name")
            else:
                return spell.cd

    def reset(self):
        self.batchedMods = {}
        self.curStats = self.baseStats.copy()

    def statMod(self, precedence):
        if not self.batchedMods.get(precedence):
            self.batchedMods[precedence] = []

        def batchStatChange(fn):
            self.batchedMods[precedence] += [fn]

        return batchStatChange

    def updateBuffEffects(self):
        self.reset()
        for name, buff in self.buffTracker.buffs.items():
            buff.whileActive(self)

    def recalculateBuffs(self):
        self.updateBuffEffects()
        precedences = sorted(self.batchedMods.keys())
        for precedence in precedences:
            for mod in self.batchedMods[precedence]:
                mod()

    def recalculateSpells(self):
        moreStats = {"hastePercent": self.getHaste(),
                    "masteryPercent": self.getMastery(),
                    "critPercent": self.getCrit(),
                    "versPercent": self.getVers(),
                    "buffTracker": self.buffTracker
                    }

        curStats = {**self.curStats.copy(), **moreStats}

        self.spellTracker.updateFields(curStats)
        self.spellTracker.gcd.updateFields(curStats)

    def recalculate(self):
        if self.buffListChanged():
            self.recalculateBuffs()

        # if self.statsChanged
        if True:
            self.recalculateSpells()

    def buffListChanged(self):
        newBuffList =  self.buffTracker.getBuffList()
        changed = newBuffList != self.lastBuffList
        if changed:
            self.lastBuffList = newBuffList

        return changed

    def cast(self, spellName):
        def default(player):
            pass

        onCast = self.spellTracker.cast(spellName)
        if onCast is not None:
            onCast(self)
            if spellName != "Glimmer of Light":
                pass#print(spellName)

            return onCast

    def tick(self, n):
        self.buffTracker.subDuration(n)
        self.spellTracker.subCD(n)
        self.glimmerTracker.subDuration(n)

    def canCast(self, spellName=None):
        return self.spellTracker.canCast(spellName)

    def getRating(self, key):
        return self.curStats.get(key, 0)

    def getBaseRating(self, key):
        return self.baseStats.get(key, 0)

    def getHaste(self):
        return (1 + self.curStats["hasteRating"] / 68 / 100) * 1 - 1

    def getMastery(self):
        return (BASEMASTERY*100 + self.curStats["masteryRating"] / 48) / 100

    def getCrit(self):
        return BASECRIT + self.curStats["critRating"] / 72 / 100

    def getVers(self):
        return BASEVERS + self.curStats["versRating"] / 85 / 100


class Sim:

    def __init__(self, player, simTime):
        self.player = player
        self.procTracker = PPMTracker(self.player)

        self.healing = 0
        self.breakdown = {}
        self.casts = {}
        self.hits = {}
        self.combatTime = 0

        self.simTime = simTime

    def clear(self):
        self.procTracker = PPMTracker(self.player)

        self.healing = 0
        self.breakdown = {}
        self.casts = {}
        self.hits = {}
        self.combatTime = 0

    def printBreakdown(self, shouldPrint=True):
        longestKey = 0
        longestVal = 0
        total = 1
        for k, v in self.breakdown.items():
            total += v
            rv = round(v)
            if len(k) > longestKey:
                longestKey = len(k)

            if len(str(rv)) > longestVal:
                longestVal = len(str(rv))

        toRet = f"\nBreakdown over {round(self.combatTime)}s\n" \
                f"{'Spell'.ljust(longestKey+3)}{'Amount'.ljust(longestVal+3)}{'Percent'.ljust(9)}{'Casts'.ljust(7)}{'Hits'.ljust(6)}\n"

        sortedKeys = sortKeys(self.breakdown)

        for k in sortedKeys:
            v = self.breakdown.get(k)

            rv = round(v)
            p = round((v/total)*1000)/10
            pstr = (str(p) + "%").rjust(6)
            cstr = str(self.casts.get(k,0)).rjust(3)
            hstr = str(self.hits.get(k,0)).rjust(3)

            toRet += f"{k.ljust(longestKey)} : {str(rv).rjust(longestVal)} : {pstr} : {cstr} : {hstr}\n"
        if shouldPrint:
            print(toRet)

        return toRet

    def heal(self, amt, spellName, beaconPercent=0.4, hits=1):
        #print(round(amt))
        bamt = amt * beaconPercent
        self.healing += amt + bamt

        # non-beacon
        if not self.breakdown.get(spellName):
            self.breakdown[spellName] = amt
        else:
            self.breakdown[spellName] += amt

        if not self.casts.get(spellName):
            self.casts[spellName] = 1
        else:
            self.casts[spellName] += 1

        if not self.hits.get(spellName):
            self.hits[spellName] = hits
        else:
            self.hits[spellName] += hits

        # beacon
        if not self.breakdown.get("Beacon of Light"):
            self.breakdown["Beacon of Light"] = bamt
        else:
            self.breakdown["Beacon of Light"] += bamt

        if not self.hits.get("Beacon of Light"):
            self.hits["Beacon of Light"] = 1
        else:
            self.hits["Beacon of Light"] += 1

    def cast(self, spellName):
        onCast = self.player.cast(spellName)
        if onCast is not None:
            onCast(self)
            timeStr = str(round(self.combatTime*10)/10).ljust(6)
            if spellName != "Glimmer of Light":
                pass#print(timeStr, spellName)

    def run(self):
        player = self.player
        player.recalculate()

        def cast(spellName):
            self.cast(spellName)

        def cd(spellName):
            return player.getSpellCD(spellName)

        def wait():
            player.recalculate()
            player.tick(gameTimePassed)

        """
        print(cd("Holy Shock"))
        cast("Holy Shock")
        print(cd("Holy Shock"))
        player.spellTracker.spells["Holy Shock"].subCD(1)
        print(cd("Holy Shock"))

        player.buffTracker.apply(player.buffTracker.ineffable)
        player.recalculate()
        print("Ineffable")
        print(cd("Holy Shock"))
        cast("Holy Shock")
        print(cd("Holy Shock"))
        player.spellTracker.spells["Holy Shock"].subCD(1)
        print(cd("Holy Shock"))
        """

        while not self.simTime or (self.combatTime <= self.simTime):
            #print(self.combatTime)

            sleep(INTERVAL)

            gameTimePassed = GAMERATE
            self.combatTime += gameTimePassed

            gcdlen = player.getSpellMaxCD("gcd")
            csCharges = player.spellTracker.spells["Crusader Strike"].charges


            if player.canCast("Holy Avenger") and cd("Avenging Wrath") < 1:
                cast("Holy Avenger")

            if player.buffTracker.isActive("Holy Avenger") and cd("Avenging Wrath") < 1:
                cast("Avenging Wrath")
                wait()
                continue

            if cd("Avenging Wrath") < 2 and cd("Holy Avenger") < 1:
                wait()
                continue

            if player.buffTracker.isActive("Avenging Wrath"):
                cast("Holy Shock")

                if cd("Holy Shock") < gcdlen:
                    wait()
                    continue

                if csCharges == 2:
                    if cd("Holy Shock") > 1.5:
                        cast("Crusader Strike")

                if csCharges == 1:
                    if cd("Crusader Strike") < gcdlen:
                        cast("Light of Dawn")

                    if cd("Holy Shock") < 1.5:
                        wait()

                    cast("Crusader Strike")

                if csCharges == 0:
                    if cd("Holy Shock") < gcdlen:
                        wait()

                    cast("Light of Dawn")

                    if cd("Holy Shock") < 1.5:
                        wait()

                    cast("Crusader Strike")

            else:
                cast("Holy Shock")
                if cd("Holy Shock") < gcdlen:
                    wait()
                    continue

                if csCharges < 2:
                    cast("Light of Dawn")
                else:
                    cast("Crusader Strike")



            player.recalculate()
            player.tick(gameTimePassed)
            """
            gcd.subCD(gameTimePassed)
            for spell in spells:
            for spell in spells:
                spell.subCD(gameTimePassed)

            glimmerTracker.subDuration(gameTimePassed)
            buffTracker.subDuration(gameTimePassed)

            if buffTracker.isActive("Avenging Wrath"):
                self.crit = self.baseCrit + 0.2

            if not gcd.canCast():
                continue

            if canCast(avengingWrath):
                cast(avengingWrath)

            if canCast(holyShock):
                cast(holyShock)
            """
            """
            # no-cooldown rotation
            if canCast(holyShock):
                cast(holyShock)
                #continue
            elif holyShock.curcd < 1.5:
                pass
                #continue
            else:
                if canCast(holyShock):
                    cast(lightOfDawn)
                    #continue
                elif (lightOfDawn.curcd < 1) & (crusaderStrike.charges < 2) & (crusaderStrike.curcd > 1):
                    cast(lightOfDawn)
                    #continue
                elif crusaderStrike.charges == 2:
                    cast(crusaderStrike)
                    #continue
                else:
                    if canCast(holyShock):
                        cast(crusaderStrike)
                        #continue
            """
            #print(self.printBreakdown(shouldPrint=False), end="\r")

        return self.healing / self.combatTime


#player = Player(2200, 1273, 852, 357, {"Avenger's Might": 2})

simTime = 30
numIterations = 100

for r in range(0, 9):
    iReduction = r*0.2

    resultList = []
    for i in range(numIterations):
        player = Player(2200, 1273, 852, 357, {"Avenger's Might": 2}, ineffableReduction=iReduction)

        sim = Sim(player, simTime)
        resultList.append(sim.run())
        player.reset()

    print(f"{simTime}s hps over {numIterations} iterations for {iReduction*100}% ineffable truth reduction:")
    avg = statistics.mean(resultList)
    stdev = statistics.stdev(resultList)
    most = max(resultList)
    least = min(resultList)

    print("Mean hps: ", avg)
    print("stdev: ", stdev)
    print("Max: ", most)
    print("Min: ", least)
    print()



#sim.printBreakdown()
#print(round(hps), "hps")

#1
#Mean hps:  219195.1476473682
#stdev:  31083.04569363025
#2
#Mean hps:  215808.4926172427
#stdev:  30895.721202018678
#3
#Mean hps:  214986.85197686745
#stdev:  30267.67877823458
#4
#Mean hps:  216997.4350096554
#stdev:  30088.29833556403
#5
#Mean hps:  215929.37237390748
#stdev:  31094.312570215978