
import sys
import os
from glob import glob
import json
from copy import copy
import CGData

def log(eStr):
    sys.stderr.write("LOG: %s\n" % (eStr))
    #errorLogHandle.write("LOG: %s\n" % (eStr))


def warn(eStr):
    sys.stderr.write("WARNING: %s\n" % (eStr))
    #errorLogHandle.write("WARNING: %s\n" % (eStr))


def error(eStr):
    sys.stderr.write("ERROR: %s\n" % (eStr))
    #errorLogHandle.write("ERROR: %s\n" % (eStr))


class CGIDTable:
    
    def __init__(self):
        self.idTable = {}
    
    def alloc( self, iType, iName ):
        if iType not in self.idTable:
            self.idTable[ iType ] = {}
        if iName not in self.idTable[ iType ]:
            self.idTable[ iType ][ iName ] = len( self.idTable[ iType ] )
    
    def get( self, iType, iName ):
        return self.idTable[ iType ][ iName ]


class BrowserCompiler:

    def __init__(self):
        self.setHash = {}
        self.pathHash = {}
        self.outDir = "out"

    def scanDirs(self, dirs):
        for dir in dirs:
            log("SCANNING DIR: %s" % (dir))
            for path in glob(os.path.join(dir, "*.json")):
                handle = open(path)
                try:
                    data = json.loads(handle.read())
                except ValueError, e:
                    error("BAD JSON in " + path + " " + str(e) )
                    data = None
                handle.close()
                
                if data is not None and 'name' in data and data['name'] is not None\
                and 'type' in data\
                and CGData.has_type(data['type']):
                    if not data['type'] in self.setHash:
                        self.setHash[ data['type'] ] = {}
                        self.pathHash[ data['type'] ] = {}
                        
                    if data['name'] in self.setHash[data['type']]:
                        error("Duplicate %s file %s" % (
                            data['type'], data['name']))
                    self.setHash[data['type']][data['name']] = CGData.lightLoad( path )
                    self.pathHash[data['type']][data['name']] = path
                    log("FOUND: " + data['type'] +
                        "\t" + data['name'] + "\t" + path)
                else:
                    warn("Unknown file type: %s" % (path))
    
    def __iter__(self):
        return self.setHash.__iter__()
    
    def __getitem__(self, i):
        return self.setHash[ i ]
    
    def linkObjects(self):
        """
        Scan found object records and determine if the data they link to is
        avalible
        """
        oMatrix = {}
        for oType in self.setHash:
            if issubclass( CGData.get_type( oType ), CGData.CGGroupMember ):
                gMap = {}
                for oName in self.setHash[ oType ]:
                    oObj = self.setHash[ oType ][ oName ]
                    if oObj.getGroup() not in gMap:
                        gMap[ oObj.getGroup() ] = CGData.CGGroupBase( oObj.getGroup() )
                    gMap[ oObj.getGroup() ].put( oObj )
                oMatrix[ oType ] = gMap
            else:
                oMatrix[ oType ] = self.setHash[ oType ]
        
        # Now it's time to check objects for their dependencies
        readyMatrix = {}
        for sType in oMatrix:
            for sName in oMatrix[ sType ]:
                sObj = oMatrix[ sType ][ sName ]
                lMap = sObj.getLinkMap()
                isReady = True
                for lType in lMap:
                    if not oMatrix.has_key( lType ):
                        warn( "%s missing data type %s" % (sName, lType) )
                        isReady = False
                    else:
                        for lName in lMap[ lType ]:
                            if not oMatrix[lType].has_key( lName ):
                                warn( "%s %s missing data %s %s" % ( sType, sName, lType, lName ) )
                                isReady = False
                if not sObj.isLinkReady():
                    warn( "%s %s not LinkReady" % ( sType, sName ) )
                elif isReady:
                    if not sType in readyMatrix:
                        readyMatrix[ sType ] = {}
                    readyMatrix[ sType ][ sName ] = sObj
        
        for rType in readyMatrix:
            log( "READY %s: %s" % ( rType, ",".join(readyMatrix[rType].keys()) ) ) 

        for mergeType in CGData.mergeObjects:
            mType = CGData.get_type( mergeType )
            print mType
            selectTypes = mType.typeSet
            selectSet = {}
            try:
                for sType in selectTypes:
                    selectSet[ sType ] = readyMatrix[ sType ] 
            except KeyError:
                error("missing data type %s" % (sType) )
                continue
            mObjList = self.setEnumerate( mType, selectSet )
            for mObj in mObjList:
                if mergeType not in readyMatrix:
                    readyMatrix[ mergeType ] = {}
                readyMatrix[ mergeType ][ mObj.getName() ] = mObj
        
        self.readyMatrix = readyMatrix                    
        
    def setEnumerate( self, mergeType, a, b={} ):
        """
        This is an recursive function to enumerate possible sets of elements in the 'a' hash
        a is a map of types ('probeMap', 'clinicalMatrix', ...), each of those is a map
        of cgBaseObjects that report getLinkMap requests
        """
        #print "Enter", " ".join( (b[c].getName() for c in b) )
        curKey = None
        for t in a:
            if not t in b:
                curKey = t
        
        if curKey is None:
            #print " ".join( ( "%s:%s:%s" % (c, b[c].getName(), str(b[c].getLinkMap()) ) for c in b) )
            log( "Merging %s" % ",".join( ( "%s:%s" %(c,b[c].getName()) for c in b) ) )  
            mergeObj = mergeType()
            mergeObj.merge( **b )
            return [ mergeObj ]
        else:
            out = []
            for i in a[curKey]:
                #print "Trying", curKey, i
                c = copy(b)
                sObj = a[curKey][i] #the object selected to be added next
                lMap = sObj.getLinkMap()
                valid = True
                for lType in lMap:
                    if lType in c:
                        if c[lType].getName() not in lMap[lType]:
                            #print c[lType].getName(), "not in", lMap[lType]
                            valid = False
                for sType in c:
                    slMap = c[sType].getLinkMap()
                    for slType in slMap:
                        if curKey == slType:
                            if sObj.getName() not in slMap[slType]:
                                #print a[curKey][i].getName(), "not in",  slMap[slType]
                                valid = False
                if valid:
                    c[ curKey ] = sObj
                    out.extend( self.setEnumerate( mergeType, a, c ) )
            return out
        return []

    def buildIDs(self):
        log( "Building Common ID tables" )
        self.idTable = CGIDTable()        
        for rType in self.readyMatrix:
            if issubclass( CGData.get_type( rType ), CGData.CGSQLObject ):
                for rName in self.readyMatrix[ rType ]:
                    self.readyMatrix[ rType ][ rName ].buildIDs( self.idTable )

    def genSQL(self):
        log( "Writing SQL" )        
        for rType in self.readyMatrix:
            if issubclass( CGData.get_type( rType ), CGData.CGSQLObject ):
                for rName in self.readyMatrix[ rType ]:
                    sHandle = self.readyMatrix[ rType ][ rName ].genSQL( self.idTable )
                    if sHandle is not None:
                        oHandle = open( os.path.join( self.outDir, "%s.%s.sql" % (rType, rName ) ), "w" )
                        for line in sHandle:
                            oHandle.write( line )
                        oHandle.close()
    
    
