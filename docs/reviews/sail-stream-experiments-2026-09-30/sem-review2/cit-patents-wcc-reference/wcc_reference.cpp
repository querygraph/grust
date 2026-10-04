// Dataset-bounded exact WCC reference; no threading or external dependencies.
#include <algorithm>
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <sys/resource.h>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>

namespace {
constexpr uint64_t max_supported_id = 6009554;
constexpr uint64_t rss_guard_bytes = 512ULL * 1024 * 1024;

uint64_t number(const char* text) {
    const std::string value(text);
    if (value.empty() || value.find_first_not_of("0123456789") != std::string::npos)
        throw std::runtime_error("invalid unsigned decimal argument");
    return std::stoull(value);
}

uint64_t peak_rss() {
    rusage usage{};
    if (getrusage(RUSAGE_SELF, &usage) != 0) throw std::runtime_error("getrusage failed");
#ifdef __APPLE__
    return static_cast<uint64_t>(usage.ru_maxrss);
#else
    return static_cast<uint64_t>(usage.ru_maxrss) * 1024;
#endif
}

void check_rss() {
    if (peak_rss() > rss_guard_bytes) throw std::runtime_error("observed RSS guard exceeded");
}

struct Input {
    FILE* file;
    Input(const char* path, uint64_t expected_bytes) : file(std::fopen(path, "rb")) {
        if (!file) throw std::runtime_error("cannot open input");
        struct stat st{};
        if (fstat(fileno(file), &st) != 0 || !S_ISREG(st.st_mode) || st.st_size < 0 ||
            static_cast<uint64_t>(st.st_size) != expected_bytes)
            throw std::runtime_error("input byte count/type differs from declared rows");
    }
    Input(const Input&) = delete;
    Input& operator=(const Input&) = delete;
    ~Input() { if (file) std::fclose(file); }
    uint64_t id() {
        unsigned char raw[8];
        if (std::fread(raw, 1, sizeof(raw), file) != sizeof(raw)) throw std::runtime_error("truncated input");
        uint64_t value = 0;
        for (unsigned i = 0; i < 8; ++i) value |= static_cast<uint64_t>(raw[i]) << (8 * i);
        return value;
    }
};

void write_id(FILE* file, uint64_t value) {
    unsigned char raw[8];
    for (unsigned i = 0; i < 8; ++i) raw[i] = static_cast<unsigned char>(value >> (8 * i));
    if (std::fwrite(raw, 1, sizeof(raw), file) != sizeof(raw)) throw std::runtime_error("output write failed");
}

uint32_t find_root(std::vector<uint32_t>& parent, uint32_t value) {
    while (parent[value] != value) {
        parent[value] = parent[parent[value]];
        value = parent[value];
    }
    return value;
}
}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc != 9) throw std::runtime_error("usage: wcc vertices.i64le edges.i64le output.i64le min_id max_id vertex_rows edge_rows positive-range-wcc-v1");
        const uint64_t low = number(argv[4]), high = number(argv[5]);
        const uint64_t vertices = number(argv[6]), edges = number(argv[7]);
        // argv[8] is an explicit contract marker, not a generic signed-ID mode.
        if (std::string(argv[8]) != "positive-range-wcc-v1") throw std::runtime_error("wrong contract marker");
        if (low < 1 || low > high || high > max_supported_id || vertices > high - low + 1 ||
            vertices > std::numeric_limits<uint32_t>::max() || edges > std::numeric_limits<uint64_t>::max()/16)
            throw std::runtime_error("dataset-specific positive ID/count range rejected");
        Input vertex_input(argv[1], vertices * 8), edge_input(argv[2], edges * 16);
        const size_t slots = static_cast<size_t>(high + 1);
        std::vector<uint32_t> parent(slots), size(slots), minimum(slots);
        std::vector<uint8_t> flags(slots); // bit 0: declared vertex; bit 1: incident edge
        const uint64_t state_bytes = slots * (3 * sizeof(uint32_t) + sizeof(uint8_t));
        if (state_bytes > 128ULL * 1024 * 1024) throw std::runtime_error("state allocation contract exceeded");
        check_rss();
        auto checked_id = [&](uint64_t value) {
            if (value < low || value > high) throw std::runtime_error("ID outside declared positive range");
            return static_cast<uint32_t>(value);
        };
        for (uint64_t row = 0; row < vertices; ++row) {
            const uint32_t id = checked_id(vertex_input.id());
            if (flags[id]) throw std::runtime_error("duplicate declared vertex");
            flags[id] = 1; parent[id] = id; size[id] = 1; minimum[id] = id;
        }
        uint64_t successful_unions = 0, self_loop_rows = 0;
        for (uint64_t row = 0; row < edges; ++row) {
            const uint32_t source = checked_id(edge_input.id()), target = checked_id(edge_input.id());
            if (!(flags[source] & 1) || !(flags[target] & 1)) throw std::runtime_error("edge endpoint missing from vertex set");
            flags[source] |= 2; flags[target] |= 2;
            if (source == target) ++self_loop_rows;
            auto a = find_root(parent, source), b = find_root(parent, target);
            if (a != b) {
                if (size[a] < size[b]) std::swap(a, b);
                parent[b] = a; size[a] += size[b]; minimum[a] = std::min(minimum[a], minimum[b]);
                ++successful_unions;
            }
            if ((row & ((1ULL << 20) - 1)) == 0) check_rss();
        }
        uint64_t components = 0, largest = 0, largest_min = 0, isolates = 0, singleton_components = 0;
        for (uint64_t id = low; id <= high; ++id) {
            if (!(flags[id] & 1)) continue;
            if (!(flags[id] & 2)) ++isolates;
            if (parent[id] != id) continue;
            ++components;
            if (size[id] == 1) ++singleton_components;
            if (size[id] > largest || (size[id] == largest && minimum[id] < largest_min)) {
                largest = size[id]; largest_min = minimum[id];
            }
        }
        if (components + successful_unions != vertices) throw std::runtime_error("union accounting invariant failed");
        const int fd = open(argv[3], O_WRONLY | O_CREAT | O_EXCL, 0600);
        if (fd < 0) throw std::runtime_error("output must be a new private file");
        FILE* output = fdopen(fd, "wb");
        if (!output) { close(fd); throw std::runtime_error("fdopen failed"); }
        uint64_t rows = 0;
        for (uint64_t id = low; id <= high; ++id) {
            if (!(flags[id] & 1)) continue;
            write_id(output, id);
            write_id(output, minimum[find_root(parent, static_cast<uint32_t>(id))]);
            ++rows;
        }
        if (std::fclose(output) != 0) throw std::runtime_error("output close failed");
        check_rss();
        std::cout << "{\"vertex_rows\":" << vertices << ",\"edge_rows\":" << edges
                  << ",\"output_rows\":" << rows << ",\"component_count\":" << components
                  << ",\"largest_component_vertices\":" << largest
                  << ",\"largest_component_minimum_id\":" << largest_min
                  << ",\"isolated_vertices_without_incident_edges\":" << isolates
                  << ",\"singleton_components\":" << singleton_components
                  << ",\"self_loop_edge_rows\":" << self_loop_rows
                  << ",\"successful_unions\":" << successful_unions
                  << ",\"fixed_state_bytes\":" << state_bytes
                  << ",\"peak_process_rss_bytes\":" << peak_rss() << "}\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "WCC reference rejected: " << error.what() << '\n';
        return 1;
    }
}
