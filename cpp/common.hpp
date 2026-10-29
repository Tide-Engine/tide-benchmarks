#pragma once

#include <algorithm>
#include <array>
#include <bit>
#include <charconv>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <limits>
#include <numeric>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace bench {

constexpr float dt = 1.0f / 60.0f;
enum class Workload { particles, wide, churn };

struct Options {
    Workload workload = Workload::particles;
    std::uint32_t count = 1'000'000;
    std::uint32_t rate = 2'000;
    bool tagged = false;
    std::uint32_t frozen = 0;
    std::uint32_t threads = 1;
    std::uint32_t warmup = 200;
    std::uint32_t ticks = 400;
};

inline std::string_view name(Workload w) {
    switch (w) {
        case Workload::particles: return "particles";
        case Workload::wide: return "wide";
        case Workload::churn: return "churn";
    }
    throw std::runtime_error("invalid workload");
}

inline Options options(int argc, char **argv) {
    Options out;
    for (int i = 1; i < argc; i += 2) {
        const std::string_view flag(argv[i]);
        if (flag == "--help" || flag == "-h") {
            std::cout << "--workload particles|wide|churn [--count N] [--rate N] "
                         "[--tagged 0|1] [--frozen N] [--threads 1] [--warmup N] [--ticks N]\n"
                         "This comparator supports one execution thread. First particle/wide tick only spawns.\n";
            std::exit(0);
        }
        if (i + 1 >= argc) throw std::runtime_error("every option requires a value");
        const std::string_view value(argv[i + 1]);
        if (flag == "--workload") {
            if (value == "particles") out.workload = Workload::particles;
            else if (value == "wide") out.workload = Workload::wide;
            else if (value == "churn") out.workload = Workload::churn;
            else throw std::runtime_error("--workload must be particles, wide, or churn");
            continue;
        }
        std::uint32_t n = 0;
        const auto parsed = std::from_chars(value.data(), value.data() + value.size(), n);
        if (value.empty() || parsed.ec != std::errc() || parsed.ptr != value.data() + value.size() ||
            n > static_cast<std::uint32_t>(std::numeric_limits<std::int32_t>::max())) {
            throw std::runtime_error(std::string(flag) + " requires an integer between 0 and 2147483647");
        }
        if (flag == "--count") out.count = n;
        else if (flag == "--rate") out.rate = n;
        else if (flag == "--tagged" && n <= 1) out.tagged = n != 0;
        else if (flag == "--frozen") out.frozen = n;
        else if (flag == "--threads") out.threads = n;
        else if (flag == "--warmup") out.warmup = n;
        else if (flag == "--ticks") out.ticks = n;
        else throw std::runtime_error("unknown or invalid option " + std::string(flag));
    }
    if (!out.rate || !out.warmup || !out.ticks) throw std::runtime_error("rate, warmup and ticks must be positive");
    if (out.threads != 1) throw std::runtime_error("this comparator supports --threads 1 only");
    if (out.workload == Workload::particles && !out.count) throw std::runtime_error("particles count must be positive");
    return out;
}

// Tide's Math.Hash(int2), with explicitly wrapping unsigned arithmetic.
inline std::uint32_t hash_i2(std::uint32_t x, std::uint32_t y) {
    auto word = [](std::uint32_t h, std::uint32_t value) {
        return std::rotl(h + value * 0xc2b2ae3du, 17) * 0x27d4eb2fu;
    };
    std::uint32_t h = word(word(0x165667b1u + 8u, x), y);
    h ^= h >> 15;
    h *= 0x85ebca77u;
    h ^= h >> 13;
    h *= 0xc2b2ae3du;
    h ^= h >> 16;
    return h & 0x7fffffffu;
}

struct Particle { float x, y, vx, vy; };
struct Motion {
    float position[3], velocity[3], push[3];
    float drag, bounce, radius;
};
struct Bullet { float x, y, vx, vy; std::int32_t life; };
struct Frozen {};
static_assert(sizeof(Particle) == 16 && sizeof(Motion) == 48 && sizeof(Bullet) == 20);
static_assert(sizeof(float) == 4 && std::numeric_limits<float>::is_iec559);

inline Particle particle(std::uint32_t i) {
    const auto h = hash_i2(i, 0), g = hash_i2(i, 1);
    return {float(h % 10000) * 0.01f, float(g % 10000) * 0.01f,
            float(std::int32_t(h % 201) - 100) * 0.1f, float(std::int32_t(g % 201) - 100) * 0.1f};
}

inline Motion motion(std::uint32_t i) {
    const auto h = hash_i2(i, 0), g = hash_i2(i, 1), f = hash_i2(i, 2);
    return {{float(h % 10000) * 0.01f, float(g % 10000) * 0.01f + 1.0f, float(f % 10000) * 0.01f},
            {float(std::int32_t(h % 201) - 100) * 0.1f, float(std::int32_t(g % 201) - 100) * 0.1f,
             float(std::int32_t(f % 201) - 100) * 0.1f},
            {float(std::int32_t(f % 21) - 10) * 0.05f, -9.81f, float(std::int32_t(h % 21) - 10) * 0.05f},
            float(g % 50) * 0.001f, 0.5f + float(h % 40) * 0.01f, 0.25f + float(f % 4) * 0.25f};
}

inline Bullet bullet(std::uint32_t tick, std::uint32_t i) {
    const auto h = hash_i2(tick, i);
    return {0.0f, 0.0f, float(std::int32_t(h % 201) - 100),
            float(std::int32_t(h / 201 % 201) - 100), 20 + std::int32_t(h % 160)};
}

inline void step(Particle &p) {
    const float v = p.vy - 9.81f * dt;
    const float h = p.y + v * dt;
    const bool floor = h < 0.0f;
    p.y = floor ? -h : h;
    p.vy = floor ? -v * 0.9f : v;
    const float u = p.vx;
    const float w = p.x + u * dt;
    const bool left = w < 0.0f, right = w > 100.0f;
    p.x = left ? -w : (right ? 200.0f - w : w);
    p.vx = (left || right) ? -u : u;
}

inline void step(Motion &m) {
    const float keep = 1.0f - m.drag * dt;
    const float u = (m.velocity[0] + m.push[0] * dt) * keep;
    const float v = (m.velocity[1] + m.push[1] * dt) * keep;
    const float s = (m.velocity[2] + m.push[2] * dt) * keep;
    const float y = m.position[1] + v * dt;
    const bool floor = y < m.radius;
    m.position[0] += u * dt;
    m.position[1] = floor ? m.radius * 2.0f - y : y;
    m.position[2] += s * dt;
    m.velocity[0] = u;
    m.velocity[1] = floor ? -v * m.bounce : v;
    m.velocity[2] = s;
}

inline bool step(Bullet &b) {
    b.x += b.vx * dt;
    b.y += b.vy * dt;
    --b.life;
    return b.life <= 0;
}

// Logical fields are encoded little-endian, independently of native padding.
template<std::size_t N> inline std::uint64_t item(const std::array<std::uint32_t, N> &words) {
    std::uint64_t h = 0xcbf29ce484222325ull;
    for (const auto word : words) {
        for (unsigned shift = 0; shift < 32; shift += 8) {
            h = (h ^ ((word >> shift) & 255u)) * 0x100000001b3ull;
        }
    }
    h = (h ^ (h >> 30)) * 0xbf58476d1ce4e5b9ull;
    h = (h ^ (h >> 27)) * 0x94d049bb133111ebull;
    return h ^ (h >> 31);
}

inline std::uint64_t item(const Particle &p) {
    return item(std::array{std::bit_cast<std::uint32_t>(p.x), std::bit_cast<std::uint32_t>(p.y),
                           std::bit_cast<std::uint32_t>(p.vx), std::bit_cast<std::uint32_t>(p.vy)});
}
inline std::uint64_t item(const Motion &m) {
    std::array<std::uint32_t, 12> words{};
    for (std::size_t i = 0; i < 3; ++i) {
        words[i] = std::bit_cast<std::uint32_t>(m.position[i]);
        words[3 + i] = std::bit_cast<std::uint32_t>(m.velocity[i]);
        words[6 + i] = std::bit_cast<std::uint32_t>(m.push[i]);
    }
    words[9] = std::bit_cast<std::uint32_t>(m.drag);
    words[10] = std::bit_cast<std::uint32_t>(m.bounce);
    words[11] = std::bit_cast<std::uint32_t>(m.radius);
    return item(words);
}
inline std::uint64_t item(const Bullet &b) {
    return item(std::array{std::bit_cast<std::uint32_t>(b.x), std::bit_cast<std::uint32_t>(b.y),
                          std::bit_cast<std::uint32_t>(b.vx), std::bit_cast<std::uint32_t>(b.vy),
                          static_cast<std::uint32_t>(b.life)});
}

struct Digest { std::uint64_t sum = 0, count = 0, frozen = 0; };

inline void output(const Options &o, std::string_view engine, std::string_view version,
                   std::string_view method, const Digest &digest, const std::vector<double> &samples) {
    auto sorted = samples;
    std::sort(sorted.begin(), sorted.end());
    const auto mid = sorted.size() / 2;
    const double median = sorted.size() % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) * 0.5;
    const double mean = std::accumulate(samples.begin(), samples.end(), 0.0) / double(samples.size());
    std::cout << std::fixed << std::setprecision(9)
              << "{\"benchmark\":\"versus_" << name(o.workload) << "\",\"workload\":\"" << name(o.workload)
              << "\",\"engine\":\"" << engine << "\",\"version\":\"" << version
              << "\",\"method\":\"" << method << "\",\"compiler\":\"clang " << __clang_version__
              << "\",\"count\":" << o.count << ",\"rate\":" << o.rate << ",\"tagged\":" << unsigned(o.tagged)
              << ",\"frozen\":" << o.frozen << ",\"threads\":" << o.threads << ",\"warmup\":" << o.warmup
              << ",\"ticks\":" << o.ticks << ",\"median_ms\":" << median << ",\"mean_ms\":" << mean
              << ",\"digest\":\"0x" << std::hex << std::setw(16) << std::setfill('0') << digest.sum << std::dec
              << "\",\"entity_count\":" << digest.count << ",\"moving_count\":" << digest.count - digest.frozen
              << ",\"frozen_count\":" << digest.frozen << ",\"samples_ms\":[";
    for (std::size_t i = 0; i < samples.size(); ++i) {
        if (i) std::cout << ',';
        std::cout << samples[i];
    }
    std::cout << "]}\n";
}

template<typename Simulation>
int run(int argc, char **argv, std::string_view engine, std::string_view version, std::string_view method) {
    try {
        const auto o = options(argc, argv);
        Simulation sim(o);
        for (std::uint32_t tick = 0; tick < o.warmup; ++tick) sim.tick();
        std::vector<double> samples;
        samples.reserve(o.ticks);
        for (std::uint32_t tick = 0; tick < o.ticks; ++tick) {
            const auto start = std::chrono::steady_clock::now();
            sim.tick();
            const auto end = std::chrono::steady_clock::now();
            samples.push_back(std::chrono::duration<double, std::milli>(end - start).count());
        }
        output(o, engine, version, method, sim.digest(), samples);
        return 0;
    } catch (const std::exception &e) {
        std::cerr << e.what() << '\n';
        return 2;
    }
}

} // namespace bench
