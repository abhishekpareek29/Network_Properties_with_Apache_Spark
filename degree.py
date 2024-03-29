import sys
import pandas
import networkx as nx
import matplotlib.pyplot as plt
import powerlaw as pl
from pyspark import SparkContext
from pyspark.sql import SQLContext
from pyspark.sql.types import *
from graphframes import *
from IPython.display import display


sc=SparkContext("local", "degree.py")
sqlContext = SQLContext(sc)

def check_powerlaw(distribution):
  y = distribution.rdd.map(lambda x: x[1]).collect()
  results = pl.Fit(y)
  return (results.power_law.alpha)

''' return the simple closure of the graph as a graphframe.'''
def simple(g):


	# Extract edges and make a data frame of "flipped" edges
	edges = g.edges

	# Edges is a Pyspark DataFrame data Structure
	edge_rdd = edges.rdd.map(lambda x: (x[1],x[0]))
	#print (edge_rdd.take(5))
	#exit()

	# Combine old and new edges. Distinctify them
	flip_df = sqlContext.createDataFrame(edge_rdd,['src','dst'])
	#flip_df = sqlContext.createDataFrame(edge_rdd,['src','dst'])
	new_edges = edges.unionAll(flip_df).distinct()
	# print new_edges.collect()
	#print new_edges.dropDuplicates().count()

	# Filter to eliminate self-loops
	print new_edges.show()
	# A multigraph with loops will be closured to a simple graph
	# If we try to undirect an undirected graph, no harm done
	g = GraphFrame(g.vertices, new_edges)

	return g



'''Return a data frame of the degree distribution of each edge in\
	the provided graphframe '''
def degreedist(g):
	# Generate a DF with degree,count
	cnt = g.inDegrees.selectExpr('id as id','inDegree as degree').groupBy('degree').count()
	return cnt


''' Read in an edgelist file with lines of the format id1<delim>id2
	and return a corresponding graphframe. If "large" we assume
	a header row and that delim = " ", otherwise no header and
	delim = ","'''
def readFile(filename, large, sqlContext=sqlContext):
	lines = sc.textFile(filename)
	print(lines.take(3))

	if large:
		delim=" "
		# Strip off header row.
		lines = lines.mapPartitionsWithIndex(lambda ind,it: iter(list(it)[1:]) if ind==0 else it)
	else:
		delim=","

	# Extract pairs from input file and convert to data frame matching
	# schema for graphframe edges.
	pairs = lines.map(lambda s: s.split(delim))
	e = sqlContext.createDataFrame(pairs,['src','dst']).distinct()

	# Extract all endpoints from input file (hence flatmap) and create
	# data frame containing all those node names in schema matching
	# graphframe vertices
	v = e.selectExpr('src as id').unionAll(e.selectExpr('dst as id')).distinct()

	# Create graphframe g from the vertices and edges.
	g = GraphFrame(v, e)

	return g


# main stuff

# If you got a file, yo, I'll parse it.
if len(sys.argv) > 1:
	filename = sys.argv[1]
	if len(sys.argv) > 2 and sys.argv[2]=='large':
		large=True
	else:
		large=False

	print("Processing input file " + filename)
	g = readFile(filename, large)

	print("Original graph has " + str(g.edges.count()) + " directed edges and " + str(g.vertices.count()) + " vertices.")


	g2 = simple(g)
	edges = g2.edges.count()/2
	#edges.show()
	print("Simple graph has " + str(edges) + " undirected edges.")

	distrib = degreedist(g2)
	distrib.show()
	nodecount = g2.vertices.count()
	print("Graph has " + str(nodecount) + " vertices.")

	out = filename.split("/")[-1]
	print("Writing distribution to file " + out + ".csv")
	distrib.toPandas().to_csv(out + ".csv")
	gamma = check_powerlaw(distrib)
	print('gamma: {}'.format(gamma))

# Otherwise, generate some random graphs.
else:
	print("Generating random graphs.")
	vschema = StructType([StructField("id", IntegerType())])
	eschema = StructType([StructField("src", IntegerType()),StructField("dst", IntegerType())])

	gnp1 = nx.gnp_random_graph(100, 0.05, seed=1234)
	gnp2 = nx.gnp_random_graph(2000, 0.01, seed=5130303)
	gnm1 = nx.gnm_random_graph(100,1000, seed=27695)
	gnm2 = nx.gnm_random_graph(1000,100000, seed=9999)

	todo = {"gnp1": gnp1, "gnp2": gnp2, "gnm1": gnm1, "gnm2": gnm2}
	for gx in todo:
		print("Processing graph " + gx)
		v = sqlContext.createDataFrame(sc.parallelize(todo[gx].nodes()), vschema)
		e = sqlContext.createDataFrame(sc.parallelize(todo[gx].edges()), eschema)
		g = simple(GraphFrame(v,e))
		distrib = degreedist(g)
		print("Writing distribution to file " + gx + ".csv")
		distrib.toPandas().to_csv(gx + ".csv")
		gamma = check_powerlaw(distrib)
		print('gamma for {}: {}'.format(gx, gamma))
