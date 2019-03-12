# Metanode
A Python package for storing and operating on data in Maya. The Metanode is a class that wraps a Maya network node in a 
scene. The class offers a standardized interface for querying and editing data on its network node. The network node 
stores information about the scene without the need for a extra file.

## Getting Started
To create your own Metanode create a class that inherits from Metanode in core.py. Overwrite the attr class method with
a dictionary of the attributes you wish to create on the network node. The key should be the attribute name with values 
that are the arguments for adding the attribute.

Once you have your new Metanode class generate it in a Maya scene.

```
my_meta = module.MetanodeSubClass.create('Name')
```

After a Metanode is created you can re-wrap it by initializing the class with the network node as a PyMel object.

```
network_node = pymel.core.PyNode('Name')
module.MetanodeSubClass(network_node)
```

## Authors

* **Kyle Mistlin-Rude**
* **Andrew Christophersen**
* **Adam Perin**
