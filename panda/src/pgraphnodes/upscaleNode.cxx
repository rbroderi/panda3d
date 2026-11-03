/**
 * PANDA 3D SOFTWARE
 * Copyright (c) Carnegie Mellon University.  All rights reserved.
 *
 * All use of this software is subject to the terms of the revised BSD
 * license.  You should have received a copy of this license along
 * with this source code in a file named "LICENSE."
 *
 * @file upscaleNode.cxx
 * @author rbroderi
 * @date 2026-11-03
 */

#include "pandabase.h"
#include "upscaleNode.h"
#include "cullTraverser.h"
#include "cullableObject.h"
#include "cullHandler.h"
#include "geomDrawCallbackData.h"
#include "omniBoundingVolume.h"
#include "config_pgraph.h"

TypeHandle UpscaleNode::_type_handle;

/**
 * Creates an UpscaleNode with the given name.  Give it its textures, and each
 * frame its jitter.
 */
UpscaleNode::
UpscaleNode(std::string name) :
  PandaNode(std::move(name)),
  _upscaler(new UpscaleNode::Upscaler(this))
{
  set_internal_bounds(new OmniBoundingVolume);
  set_renderable();
}

/**
 *
 */
UpscaleNode::
UpscaleNode(const UpscaleNode &copy) :
  PandaNode(copy),
  _upscaler(new UpscaleNode::Upscaler(*copy._upscaler))
{
  _upscaler->_node = this;
}

/**
 * Returns a newly-allocated Node that is a shallow copy of this one.  It will
 * be a different Node pointer, but its internal data may or may not be shared
 * with that of the original Node.
 */
PandaNode *UpscaleNode::
make_copy() const {
  return new UpscaleNode(*this);
}

/**
 * Returns true if it is generally safe to combine this particular kind of
 * PandaNode with other kinds of PandaNodes of compatible type, adding
 * children or whatever.  For instance, an LODNode should not be combined with
 * any other PandaNode, because its set of children is meaningful.
 */
bool UpscaleNode::
safe_to_combine() const {
  return false;
}

/**
 * Adds the node's contents to the CullResult we are building up during the
 * cull traversal, so that it will be drawn at render time.  For most nodes
 * other than GeomNodes, this is a do-nothing operation.
 */
void UpscaleNode::
add_for_draw(CullTraverser *trav, CullTraverserData &data) {
  if (pgraph_cat.is_spam()) {
    pgraph_cat.spam()
      << "Found " << *this << " in state " << *data._state
      << " draw_mask = " << data._draw_mask << "\n";
  }

  // As a ComputeNode does: a CullableObject without Geoms, which calls the
  // Upscaler where it is drawn.
  CullableObject object(nullptr, data._state,
                        data.get_internal_transform(trav));
  object.set_draw_callback(_upscaler);
  trav->get_cull_handler()->record_object(std::move(object), trav);
}

/**
 *
 */
void UpscaleNode::
output(std::ostream &out) const {
  PandaNode::output(out);
}

/**
 * Returns what a draw upscales with, as the given thread's pipeline stage
 * sees it.
 */
UpscaleNode::Params UpscaleNode::
get_params(Thread *current_thread) const {
  Upscaler::CDReader cdata(_upscaler->_cycler, current_thread);
  return cdata->_params;
}

/**
 *
 */
UpscaleNode::Upscaler::
Upscaler(UpscaleNode *node) :
  _node(node)
{
}

/**
 *
 */
UpscaleNode::Upscaler::
Upscaler(const Upscaler &copy) :
  _cycler(copy._cycler),
  _node(copy._node)
{
}

/**
 * Asks the GSG to upscale, where the node is drawn.
 */
void UpscaleNode::Upscaler::
do_callback(CallbackData *cbdata) {
  GeomDrawCallbackData *data = (GeomDrawCallbackData *)cbdata;
  GraphicsStateGuardianBase *gsg = data->get_gsg();

  gsg->dispatch_upscale(_node, Thread::get_current_thread());

  // No need to upcall; we don't have any geometry, after all.
}

/**
 *
 */
CycleData *UpscaleNode::Upscaler::CData::
make_copy() const {
  return new CData(*this);
}
