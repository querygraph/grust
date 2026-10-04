/* A plain host baseline: floating-point throughput, sequential memory, random memory.
 *   cc -O2 -o baseline baseline.c -lpthread && ./baseline [threads]
 * Each test runs on one thread and then on `threads` threads (default: online CPUs).
 * Prints one JSON object. Portable C99 + pthreads; no vector hints beyond -O2. */
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <unistd.h>

static double now(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec + t.tv_nsec * 1e-9;
}

enum { SMALL = 1 << 12 };                 /* 4096 doubles: 32 KiB, inside L1 */
#define BIG ((size_t)1 << 26)             /* 2^26 eight-byte words: 512 MiB per thread */

typedef struct { int kind; double result; double seconds; } job;

/* 1. flops: y = a*x + y over arrays in L1, two flops per element. */
static void flops(job *j) {
    static __thread double x[SMALL], y[SMALL];
    for (int i = 0; i < SMALL; i++) { x[i] = i * 0.5; y[i] = 1.0; }
    const int rounds = 200000;
    double a = 1.000001, start = now();
    for (int r = 0; r < rounds; r++)
        for (int i = 0; i < SMALL; i++) y[i] = a * x[i] + y[i];
    j->seconds = now() - start;
    j->result = 2.0 * rounds * SMALL / j->seconds / 1e9;   /* GFLOP/s */
    volatile double sink = y[7]; (void)sink;
}

/* 2. stream: sum 512 MiB sequentially, four passes. GiB/s. */
static void stream(job *j) {
    uint64_t *v = malloc(BIG * 8);
    for (size_t i = 0; i < BIG; i++) v[i] = i;
    uint64_t sum = 0; double start = now();
    for (int pass = 0; pass < 4; pass++)
        for (size_t i = 0; i < BIG; i++) sum += v[i];
    j->seconds = now() - start;
    j->result = 4.0 * BIG * 8 / j->seconds / (1 << 30);
    volatile uint64_t sink = sum; (void)sink;
    free(v);
}

/* 3. random: 2^25 dependent reads through a random cycle over 512 MiB. ns per read. */
static void chase(job *j) {
    uint64_t *v = malloc(BIG * 8);
    for (size_t i = 0; i < BIG; i++) v[i] = i;
    uint64_t s = 88172645463325252ULL;
    for (size_t i = BIG - 1; i > 0; i--) {              /* Sattolo: one cycle */
        s ^= s << 13; s ^= s >> 7; s ^= s << 17;
        size_t k = s % i; uint64_t t = v[i]; v[i] = v[k]; v[k] = t;
    }
    const size_t reads = (size_t)1 << 25;
    uint64_t at = 0; double start = now();
    for (size_t i = 0; i < reads; i++) at = v[at];
    j->seconds = now() - start;
    j->result = j->seconds / reads * 1e9;
    volatile uint64_t sink = at; (void)sink;
    free(v);
}

static void *run(void *p) {
    job *j = p;
    if (j->kind == 0) flops(j); else if (j->kind == 1) stream(j); else chase(j);
    return NULL;
}

int main(int argc, char **argv) {
    int threads = argc > 1 ? atoi(argv[1]) : (int)sysconf(_SC_NPROCESSORS_ONLN);
    const char *names[] = {"flops_gflops", "stream_gib_per_s", "random_read_ns"};
    printf("{\"threads\": %d", threads);
    for (int kind = 0; kind < 3; kind++) {
        job one = {kind, 0, 0};
        run(&one);
        pthread_t ids[256]; job jobs[256];
        for (int t = 0; t < threads; t++) { jobs[t].kind = kind; pthread_create(&ids[t], NULL, run, &jobs[t]); }
        double total = 0;
        for (int t = 0; t < threads; t++) { pthread_join(ids[t], NULL); total += jobs[t].result; }
        /* flops and stream add up across threads; a read latency is averaged. */
        printf(", \"%s_1\": %.2f, \"%s_all\": %.2f", names[kind], one.result, names[kind],
               kind == 2 ? total / threads : total);
    }
    printf("}\n");
    return 0;
}
