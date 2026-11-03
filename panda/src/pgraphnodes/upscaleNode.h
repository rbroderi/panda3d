/**
 * PANDA 3D SOFTWARE
 * Copyright (c) Carnegie Mellon University.  All rights reserved.
 *
 * All use of this software is subject to the terms of the revised BSD
 * license.  You should have received a copy of this license along
 * with this source code in a file named "LICENSE."
 *
 * @file upscaleNode.h
 * @author rbroderi
 * @date 2026-11-03
 */

#ifndef UPSCALENODE_H
#define UPSCALENODE_H

#include "pandabase.h"
#include "pandaNode.h"
#include "callbackObject.h"
#include "callbackNode.h"
#include "pointerTo.h"
#include "texture.h"
#include "luse.h"

/**
 * A special node that, where it is drawn, has the GSG's temporal upscaler
 * build the output texture from a jittered color texture, its depth and its
 * motion, as DLSS, FSR and XeSS do.  On the Vulkan renderer this is Intel's
 * XeSS Super Resolution, from a libxess.dll found at runtime (see
 * vulkan-xess-library); check GraphicsStateGuardian::get_supports_upscale()
 * after the window opens, as elsewhere it draws nothing.
 *
 * The color is linear, the depth 0 near to 1 far, and the motion two
 * components per texel, from the texel now to where it was the frame before,
 * multiplied by the motion scale into pixels of the color.  The jitter is how
 * far the camera's shift moved the scene this frame, in pixels of the color,
 * -0.5 to 0.5 each way (toward the image's later columns and rows: x, y in
 * the texture's own texel order).  The upscaler keeps its own history: set reset for the frame the
 * view cuts.  The output is written by a compute shader, so its format must
 * be one an image may be stored to; the color's size may be smaller than the
 * output's by up to three times each way.  Its bounds are infinite unless set
 * with set_bounds().
 */
class EXPCL_PANDA_PGRAPHNODES UpscaleNode : public PandaNode {
PUBLISHED:
  explicit UpscaleNode(std::string name);

  INLINE void set_color(Texture *color);
  INLINE Texture *get_color() const;
  INLINE void set_depth(Texture *depth);
  INLINE Texture *get_depth() const;
  INLINE void set_motion(Texture *motion);
  INLINE Texture *get_motion() const;
  INLINE void set_output(Texture *output);
  INLINE Texture *get_output() const;

  INLINE void set_input_size(const LVecBase2i &size);
  INLINE LVecBase2i get_input_size() const;
  INLINE void set_jitter(const LVecBase2 &jitter);
  INLINE LVecBase2 get_jitter() const;
  INLINE void set_motion_scale(const LVecBase2 &scale);
  INLINE LVecBase2 get_motion_scale() const;
  INLINE void set_exposure(PN_stdfloat exposure);
  INLINE PN_stdfloat get_exposure() const;
  INLINE void set_reset(bool reset);
  INLINE bool get_reset() const;

  MAKE_PROPERTY(color, get_color, set_color);
  MAKE_PROPERTY(depth, get_depth, set_depth);
  MAKE_PROPERTY(motion, get_motion, set_motion);
  MAKE_PROPERTY(output, get_output, set_output);
  MAKE_PROPERTY(input_size, get_input_size, set_input_size);
  MAKE_PROPERTY(jitter, get_jitter, set_jitter);
  MAKE_PROPERTY(motion_scale, get_motion_scale, set_motion_scale);
  MAKE_PROPERTY(exposure, get_exposure, set_exposure);
  MAKE_PROPERTY(reset, get_reset, set_reset);

public:
  // What one draw upscales with: a copy of the node's, as the drawing
  // thread's pipeline stage sees it.
  struct Params {
    PT(Texture) _color;
    PT(Texture) _depth;
    PT(Texture) _motion;
    PT(Texture) _output;
    // The color's part that holds the frame; zero for all of it.
    LVecBase2i _input_size = LVecBase2i(0, 0);
    LVecBase2 _jitter = LVecBase2(0, 0);
    LVecBase2 _motion_scale = LVecBase2(1, 1);
    PN_stdfloat _exposure = 1;
    bool _reset = false;
  };

  UpscaleNode(const UpscaleNode &copy);

  virtual PandaNode *make_copy() const;
  virtual bool safe_to_combine() const;

  virtual void add_for_draw(CullTraverser *trav, CullTraverserData &data);

  virtual void output(std::ostream &out) const;

  Params get_params(Thread *current_thread) const;

public:
  class EXPCL_PANDA_PGRAPHNODES Upscaler : public CallbackObject {
    friend class UpscaleNode;
  public:
    ALLOC_DELETED_CHAIN(Upscaler);
    Upscaler(UpscaleNode *node);
    Upscaler(const Upscaler &copy);

    virtual void do_callback(CallbackData *cbdata);

    class EXPCL_PANDA_PGRAPHNODES CData : public CycleData {
    public:
      INLINE CData();
      INLINE CData(const CData &copy);
      virtual CycleData *make_copy() const;
      virtual TypeHandle get_parent_type() const {
        return CallbackNode::get_class_type();
      }

      Params _params;
    };

    PipelineCycler<CData> _cycler;
    typedef CycleDataReader<CData> CDReader;
    typedef CycleDataWriter<CData> CDWriter;

    // Not a reference: the node holds this object.
    UpscaleNode *_node;
  };

private:
  // One per UpscaleNode.
  PT(Upscaler) _upscaler;

public:
  static TypeHandle get_class_type() {
    return _type_handle;
  }
  static void init_type() {
    PandaNode::init_type();
    register_type(_type_handle, "UpscaleNode",
                  PandaNode::get_class_type());
  }
  virtual TypeHandle get_type() const {
    return get_class_type();
  }
  virtual TypeHandle force_init_type() {init_type(); return get_class_type();}

private:
  static TypeHandle _type_handle;
};

#include "upscaleNode.I"

#endif
