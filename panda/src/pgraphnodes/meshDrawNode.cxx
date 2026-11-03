/**
 * PANDA 3D SOFTWARE
 * Copyright (c) Carnegie Mellon University.  All rights reserved.
 *
 * All use of this software is subject to the terms of the revised BSD
 * license.  You should have received a copy of this license along
 * with this source code in a file named "LICENSE."
 *
 * @file meshDrawNode.cxx
 * @author rbroderi
 * @date 2026-11-02
 */

#include "pandabase.h"
#include "meshDrawNode.h"
#include "cullTraverser.h"
#include "cullableObject.h"
#include "cullHandler.h"
#include "geomDrawCallbackData.h"
#include "omniBoundingVolume.h"
#include "config_pgraph.h"

TypeHandle MeshDrawNode::_type_handle;

/**
 * Creates a MeshDrawNode with the given name.  Use add_draw and  also
 * assign a shader using a ShaderAttrib.
 */
MeshDrawNode::
MeshDrawNode(std::string name) :
  PandaNode(std::move(name)),
  _drawer(new MeshDrawNode::Drawer)
{
  set_internal_bounds(new OmniBoundingVolume);
  set_renderable();
}

/**
 *
 */
MeshDrawNode::
MeshDrawNode(const MeshDrawNode &copy) :
  PandaNode(copy),
  _drawer(new MeshDrawNode::Drawer(*copy._drawer))
{
}

/**
 * Returns a newly-allocated Node that is a shallow copy of this one.  It will
 * be a different Node pointer, but its internal data may or may not be shared
 * with that of the original Node.
 */
PandaNode *MeshDrawNode::
make_copy() const {
  return new MeshDrawNode(*this);
}

/**
 * Returns true if it is generally safe to combine this particular kind of
 * PandaNode with other kinds of PandaNodes of compatible type, adding
 * children or whatever.  For instance, an LODNode should not be combined with
 * any other PandaNode, because its set of children is meaningful.
 */
bool MeshDrawNode::
safe_to_combine() const {
  return false;
}

/**
 * Adds the node's contents to the CullResult we are building up during the
 * cull traversal, so that it will be drawn at render time.  For most nodes
 * other than GeomNodes, this is a do-nothing operation.
 */
void MeshDrawNode::
add_for_draw(CullTraverser *trav, CullTraverserData &data) {
  if (pgraph_cat.is_spam()) {
    pgraph_cat.spam()
      << "Found " << *this << " in state " << *data._state
      << " draw_mask = " << data._draw_mask << "\n";
  }

  // OK, render this node.  Rendering this node means creating a
  // CullableObject for the Drawer.  We don't need to pass any Geoms,
  // however.
  CullableObject object(nullptr, data._state,
                        data.get_internal_transform(trav));
  object.set_draw_callback(_drawer);
  trav->get_cull_handler()->record_object(std::move(object), trav);
}

/**
 * Writes a brief description of the node to the indicated output stream.
 * This is invoked by the << operator.  It may be overridden in derived
 * classes to include some information relevant to the class.
 */
void MeshDrawNode::
output(std::ostream &out) const {
  PandaNode::output(out);
}

/**
 *
 */
MeshDrawNode::Drawer::
Drawer() {
}

/**
 *
 */
MeshDrawNode::Drawer::
Drawer(const Drawer &copy) :
  _cycler(copy._cycler)
{
}

/**
 * Asks the GSG to draw with the mesh shader.
 */
void MeshDrawNode::Drawer::
do_callback(CallbackData *cbdata) {
  GeomDrawCallbackData *data = (GeomDrawCallbackData *)cbdata;
  GraphicsStateGuardianBase *gsg = data->get_gsg();

  CDReader cdata(_cycler);

  for (const LVecBase3i &draw : cdata->_draws) {
    gsg->draw_mesh_tasks(draw[0], draw[1], draw[2]);
  }

  // No need to upcall; we don't have any geometry, after all.
}

/**
 * Tells the BamReader how to create objects of type MeshDrawNode.
 */
void MeshDrawNode::
register_with_read_factory() {
  BamReader::get_factory()->register_factory(get_class_type(), make_from_bam);
}

/**
 * Writes the contents of this object to the datagram for shipping out to a
 * Bam file.
 */
void MeshDrawNode::
write_datagram(BamWriter *manager, Datagram &dg) {
  PandaNode::write_datagram(manager, dg);
  manager->write_cdata(dg, _drawer->_cycler);
}

/**
 * This function is called by the BamReader's factory when a new object of
 * type MeshDrawNode is encountered in the Bam file.  It should create the
 * MeshDrawNode and extract its information from the file.
 */
TypedWritable *MeshDrawNode::
make_from_bam(const FactoryParams &params) {
  MeshDrawNode *node = new MeshDrawNode("");
  DatagramIterator scan;
  BamReader *manager;

  parse_params(params, scan, manager);
  node->fillin(scan, manager);

  return node;
}

/**
 * This internal function is called by make_from_bam to read in all of the
 * relevant data from the BamFile for the new MeshDrawNode.
 */
void MeshDrawNode::
fillin(DatagramIterator &scan, BamReader *manager) {
  PandaNode::fillin(scan, manager);
  manager->read_cdata(scan, _drawer->_cycler);
}

/**
 *
 */
CycleData *MeshDrawNode::Drawer::CData::
make_copy() const {
  return new CData(*this);
}

/**
 * Writes the contents of this object to the datagram for shipping out to a
 * Bam file.
 */
void MeshDrawNode::Drawer::CData::
write_datagram(BamWriter *manager, Datagram &dg) const {
  dg.add_uint16(_draws.size());

  for (const LVecBase3i &draw : _draws) {
    generic_write_datagram(dg, draw);
  }
}

/**
 * This internal function is called by make_from_bam to read in all of the
 * relevant data from the BamFile for the new MeshDrawNode.
 */
void MeshDrawNode::Drawer::CData::
fillin(DatagramIterator &scan, BamReader *manager) {
  int num_draws = scan.get_uint16();
  _draws.resize(num_draws);

  for (int i = 0; i < num_draws; ++i) {
    generic_read_datagram(_draws[i], scan);
  }
}
