/**
 * PANDA 3D SOFTWARE
 * Copyright (c) Carnegie Mellon University.  All rights reserved.
 *
 * All use of this software is subject to the terms of the revised BSD
 * license.  You should have received a copy of this license along
 * with this source code in a file named "LICENSE."
 *
 * @file meshDrawNode.h
 * @author rbroderi
 * @date 2026-11-02
 */

#ifndef MESHDRAWNODE_H
#define MESHDRAWNODE_H

#include "pandabase.h"
#include "pandaNode.h"
#include "callbackObject.h"
#include "callbackNode.h"
#include "pointerTo.h"
#include "small_vector.h"

/**
 * A special node, the sole purpose of which is to draw with the assigned mesh
 * shader (see Shader::make_mesh): each draw launches the given numbers of
 * task workgroups, or of mesh workgroups if the shader has no task stage.
 * The shader reads its geometry from its own inputs, such as storage buffers
 * given with set_shader_input.  It is drawn only where the GSG supports mesh
 * shaders (GraphicsStateGuardian::get_supports_mesh_shaders()).  Its bounds
 * are infinite unless set with set_bounds().
 */
class EXPCL_PANDA_PGRAPHNODES MeshDrawNode : public PandaNode {
PUBLISHED:
  explicit MeshDrawNode(std::string name);

  INLINE void add_draw(const LVecBase3i &num_groups);
  INLINE void add_draw(int num_groups_x, int num_groups_y, int num_groups_z);

  INLINE size_t get_num_draws() const;
  INLINE const LVecBase3i &get_draw(size_t i) const;
  INLINE void set_draw(size_t i, const LVecBase3i &num_groups);
  INLINE void insert_draw(size_t i, const LVecBase3i &num_groups);
  INLINE void remove_draw(size_t i);
  INLINE void clear_draws();

  MAKE_SEQ(get_draws, get_num_draws, get_draw);
  MAKE_SEQ_PROPERTY(draws, get_num_draws, get_draw, set_draw, remove_draw, insert_draw);

public:
  MeshDrawNode(const MeshDrawNode &copy);

  virtual PandaNode *make_copy() const;
  virtual bool safe_to_combine() const;

  virtual void add_for_draw(CullTraverser *trav, CullTraverserData &data);

  virtual void output(std::ostream &out) const;

public:
  class EXPCL_PANDA_PGRAPHNODES Drawer : public CallbackObject {
    friend class MeshDrawNode;
  public:
    ALLOC_DELETED_CHAIN(Drawer);
    Drawer();
    Drawer(const Drawer &copy);

    virtual void do_callback(CallbackData *cbdata);

    typedef small_vector<LVecBase3i> Draws;

    class EXPCL_PANDA_PGRAPHNODES CData : public CycleData {
    public:
      INLINE CData();
      INLINE CData(const CData &copy);
      virtual CycleData *make_copy() const;
      virtual void write_datagram(BamWriter *manager, Datagram &dg) const;
      virtual void fillin(DatagramIterator &scan, BamReader *manager);
      virtual TypeHandle get_parent_type() const {
        return CallbackNode::get_class_type();
      }

      Draws _draws;
    };

    PipelineCycler<CData> _cycler;
    typedef CycleDataReader<CData> CDReader;
    typedef CycleDataWriter<CData> CDWriter;

  };

private:
  // One per MeshDrawNode.
  PT(Drawer) _drawer;

public:
  static void register_with_read_factory();
  virtual void write_datagram(BamWriter *manager, Datagram &dg);

protected:
  static TypedWritable *make_from_bam(const FactoryParams &params);
  void fillin(DatagramIterator &scan, BamReader *manager);

public:
  static TypeHandle get_class_type() {
    return _type_handle;
  }
  static void init_type() {
    PandaNode::init_type();
    register_type(_type_handle, "MeshDrawNode",
                  PandaNode::get_class_type());
  }
  virtual TypeHandle get_type() const {
    return get_class_type();
  }
  virtual TypeHandle force_init_type() {init_type(); return get_class_type();}

private:
  static TypeHandle _type_handle;
};

#include "meshDrawNode.I"

#endif
