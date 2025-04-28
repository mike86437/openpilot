#include <iostream>
#include <chrono>
#include <cassert>
#include <random>
#include <limits>
#include <vector>
#include <algorithm>
#include <cstring> // for memcpy

#include <poll.h>
#include <sys/socket.h>
#include <unistd.h>

#include "msgq/ipc.h"
#include "msgq/visionipc/visionipc.h"
#include "msgq/visionipc/visionipc_server.h"
#include "logger/logger.h"
#include "msgq/visionipc/visionbuf.h" // Include for VisionBuf definitions

std::string get_endpoint_name(std::string name, VisionStreamType type) {
  if (messaging_use_zmq()) {
    assert(name == "camerad" || name == "navd");
    return std::to_string(9000 + static_cast<int>(type));
  } else {
    return "visionipc_" + name + "_" + std::to_string(type);
  }
}

std::string get_ipc_path(const std::string& name) {
  std::string path = "/tmp/";
  if (char* prefix = std::getenv("OPENPILOT_PREFIX")) {
    path += std::string(prefix) + "_";
  }
  return path + "visionipc_" + name;
}

// Define the horizontal shift amount here (you might want to make this configurable)
static int horizontal_shift_amount = -200;

// Forward declarations of your shift functions
void horizontal_shift_clip_rgb(const uint8_t* src, int width, int height, int stride, int shift, uint8_t* dst);
void horizontal_shift_clip_yuv(const uint8_t* y_src, const uint8_t* uv_src,
                            int width, int height, int y_stride, int uv_stride_or_offset,
                            int shift, uint8_t* dst);

VisionIpcServer::VisionIpcServer(std::string name, cl_device_id device_id, cl_context ctx) : name(name), device_id(device_id), ctx(ctx) {
  msg_ctx = Context::create();

  std::random_device rd("/dev/urandom");
  std::uniform_int_distribution<uint64_t> distribution(0, std::numeric_limits<uint64_t>::max());
  server_id = distribution(rd);
}

void VisionIpcServer::create_buffers(VisionStreamType type, size_t num_buffers, bool rgb, size_t width, size_t height) {
  // TODO: assert that this type is not created yet
  assert(num_buffers < VISIONIPC_MAX_FDS);
  int aligned_w = 0, aligned_h = 0;

  size_t size = 0;
  size_t stride = 0;
  size_t uv_offset = 0;

  if (rgb) {
    visionbuf_compute_aligned_width_and_height(width, height, &aligned_w, &aligned_h);
    size = (size_t)aligned_w * (size_t)aligned_h * 3;
    stride = aligned_w * 3;
  } else {
    size = width * height * 3 / 2;
    stride = width;
    uv_offset = width * height;
  }

  create_buffers_with_sizes(type, num_buffers, rgb, width, height, size, stride, uv_offset);
}

void VisionIpcServer::create_buffers_with_sizes(VisionStreamType type, size_t num_buffers, bool rgb, size_t width, size_t height, size_t size, size_t stride, size_t uv_offset) {
  // Create map + alloc requested buffers
  for (size_t i = 0; i < num_buffers; i++) {
    VisionBuf* buf = new VisionBuf();
    buf->allocate(size);
    buf->idx = i;
    buf->type = type;

    if (device_id) buf->init_cl(device_id, ctx);

    rgb ? buf->init_rgb(width, height, stride) : buf->init_yuv(width, height, stride, uv_offset);

    buffers[type].push_back(buf);
  }

  cur_idx[type] = 0;

  // Create msgq publisher for each of the `name` + type combos
  // TODO: compute port number directly if using zmq
  sockets[type] = PubSocket::create(msg_ctx, get_endpoint_name(name, type), false);
}


void VisionIpcServer::start_listener() {
  listener_thread = std::thread(&VisionIpcServer::listener, this);
}


void VisionIpcServer::listener() {
  std::cout << "Starting listener for: " << name << std::endl;

  const std::string ipc_path = get_ipc_path(name);
  int sock = ipc_bind(ipc_path.c_str());
  assert(sock >= 0);

  while (!should_exit) {
    // Wait for incoming connection
    struct pollfd polls[1] = {{0}};
    polls[0].fd = sock;
    polls[0].events = POLLIN;

    int ret = poll(polls, 1, 100);
    if (ret < 0) {
      if (errno == EINTR || errno == EAGAIN) continue;
      std::cout << "poll failed, stopping listener" << std::endl;
      break;
    }

    if (should_exit) break;
    if (!polls[0].revents) {
      continue;
    }

    // Handle incoming request
    int fd = accept(sock, NULL, NULL);
    assert(fd >= 0);

    VisionStreamType type = VisionStreamType::VISION_STREAM_MAX;
    int r = ipc_sendrecv_with_fds(false, fd, &type, sizeof(type), nullptr, 0, nullptr);
    assert(r == sizeof(type));

    // send available stream types
    if (type == VisionStreamType::VISION_STREAM_MAX) {
      std::vector<VisionStreamType> available_stream_types;
      for (auto& [stream_type, _] : buffers) {
        available_stream_types.push_back(stream_type);
      }
      r = ipc_sendrecv_with_fds(true, fd, available_stream_types.data(), available_stream_types.size() * sizeof(VisionStreamType), nullptr, 0, nullptr);
      assert(r == available_stream_types.size() * sizeof(VisionStreamType));
      close(fd);
      continue;
    }

    if (buffers.count(type) <= 0) {
      std::cout << "got request for invalid buffer type: " << type << std::endl;
      close(fd);
      continue;
    }

    int fds[VISIONIPC_MAX_FDS];
    int num_fds = buffers[type].size();
    VisionBuf bufs[VISIONIPC_MAX_FDS];

    for (int i = 0; i < num_fds; i++) {
      fds[i] = buffers[type][i]->fd;
      bufs[i] = *buffers[type][i];

      // Remove some private openCL/ion metadata
      bufs[i].buf_cl = 0;
      bufs[i].copy_q = 0;
      bufs[i].handle = 0;

      bufs[i].server_id = server_id;
    }

    r = ipc_sendrecv_with_fds(true, fd, &bufs, sizeof(VisionBuf) * num_fds, fds, num_fds, nullptr);

    close(fd);
  }

  std::cout << "Stopping listener for: " << name << std::endl;
  close(sock);
  unlink(ipc_path.c_str());
}



VisionBuf * VisionIpcServer::get_buffer(VisionStreamType type) {
  // Do we want to keep track if the buffer has been sent out yet and warn user?
  assert(buffers.count(type));
  auto b = buffers[type];
  return b[cur_idx[type]++ % b.size()];
}

void VisionIpcServer::send(VisionBuf * buf, VisionIpcBufExtra * extra, bool sync) {
  if (sync) {
    if (buf->sync(VISIONBUF_SYNC_FROM_DEVICE) != 0) {
      LOGE("Failed to sync buffer");
    }
  }
  assert(buffers.count(buf->type));
  assert(buf->idx < buffers[buf->type].size());

  size_t shifted_data_size = buf->width * buf->height * (buf->rgb ? 3 : buf->height * buf->width * 3 / 2 / (buf->width * buf->height));
  std::vector<uint8_t> shifted_data(shifted_data_size);
  int shift = horizontal_shift_amount;

  if (buf->rgb) {
    horizontal_shift_clip_rgb((uint8_t*)buf->addr, buf->width, buf->height, buf->stride, shift, shifted_data.data());
  } else {
    horizontal_shift_clip_yuv((uint8_t*)buf->addr, (uint8_t*)buf->addr + buf->uv_offset,
                            buf->width, buf->height, buf->stride, buf->uv_offset,
                            shift, shifted_data.data());
  }

  memcpy(buf->addr, shifted_data.data(), shifted_data_size);

  // Send over correct msgq socket
  VisionIpcPacket packet = {0};
  packet.server_id = server_id;
  packet.idx = buf->idx;
  packet.extra = *extra;

  sockets[buf->type]->send((char*)&packet, sizeof(packet));
}

VisionIpcServer::~VisionIpcServer() {
  should_exit = true;
  listener_thread.join();

  // VisionBuf cleanup
  for (auto const& [type, buf] : buffers) {
    for (VisionBuf* b : buf) {
      if (b->free() != 0) {
        LOGE("Failed to free buffer");
      }
      delete b;
    }
  }

  // Messaging cleanup
  for (auto const& [type, sock] : sockets) {
    delete sock;
  }
  delete msg_ctx;
}

// RGB Horizontal Shift and Clip (Assuming 24-bit RGB: 3 bytes per pixel)
void horizontal_shift_clip_rgb(const uint8_t* src, int width, int height, int stride, int shift, uint8_t* dst) {
  int bytesPerPixel = 3;
  int out_offset, in_offset;

  for (int y = 0; y < height; ++y) {
    for (int x = 0; x < width; ++x) {
      int original_x = x + shift;
      out_offset = y * width * bytesPerPixel + x * bytesPerPixel;

      if (original_x >= 0 && original_x < width) {
        in_offset = y * stride + original_x * bytesPerPixel;
        memcpy(dst + out_offset, src + in_offset, bytesPerPixel);
      } else {
        // Fill with black for clipped region
        memset(dst + out_offset, 0, bytesPerPixel);
      }
    }
  }
}

// Generic YUV Horizontal Shift and Clip (Handles semi-planar NV12 and planar YUV420p)
void horizontal_shift_clip_yuv(const uint8_t* y_src, const uint8_t* uv_src,
                            int width, int height, int y_stride, int uv_stride_or_offset,
                            int shift, uint8_t* dst) {
  // Process Y plane
  for (int y = 0; y < height; ++y) {
    for (int x = 0; x < width; ++x) {
      int original_x = x + shift;
      int out_offset = y * width + x;
      if (original_x >= 0 && original_x < width) {
        int in_offset = y * y_stride + original_x;
        dst[out_offset] = y_src[in_offset];
      } else {
        dst[out_offset] = 0; // Black luma
      }
    }
  }

  // Process UV plane (handle both planar and semi-planar)
  int uv_width = width / 2;
  int uv_height = height / 2;
  int bytesPerUV = 2; // For NV12 and packed formats

  for (int y = 0; y < uv_height; ++y) {
    for (int x = 0; x < uv_width; ++x) {
      int original_x = x + (shift / 2); // Adjust shift for chroma

      if (original_x >= 0 && original_x < uv_width) {
        int in_offset_uv;
        if (uv_stride_or_offset > height * width) { // Planar (YUV420p - U and V are separate)
          const uint8_t* u_src = uv_src; // U plane starts at uv_src
          const uint8_t* v_src = uv_src + uv_stride_or_offset; // V plane starts after offset
          in_offset_uv = y * uv_stride_or_offset + original_x;
          dst[height * width + y * uv_width + x] = u_src[in_offset_uv]; // U

          in_offset_uv = y * uv_stride_or_offset + original_x;
          dst[height * width + uv_height * uv_width + y * uv_width + x] = v_src[in_offset_uv]; // V
        } else { // Semi-planar (NV12 - U and V are interleaved)
          in_offset_uv = y * uv_stride_or_offset + original_x * bytesPerUV;
          dst[height * width + y * uv_width * bytesPerUV + x * bytesPerUV + 0] = uv_src[in_offset_uv + 0]; // U
          dst[height * width + y * uv_width * bytesPerUV + x * bytesPerUV + 1] = uv_src[in_offset_uv + 1]; // V
        }
      } else {
        // Fill with neutral chroma (U=128, V=128)
        int out_offset_uv = height * width + y * uv_width * bytesPerUV + x * bytesPerUV;
        dst[out_offset_uv + 0] = 128;
        dst[out_offset_uv + 1] = 128;
      }
    }
  }
}


