#include "common.hpp"

#include <flecs.h>

class Simulation {
    const bench::Options options_;
    ecs_world_t *world_ = nullptr;
    ecs_entity_t particle_id_ = 0, motion_id_ = 0, bullet_id_ = 0, frozen_id_ = 0;
    ecs_query_t *digest_query_ = nullptr;
    std::uint32_t tick_ = 0;
    bool ready_ = false;

    ecs_entity_t entity(const char *name) {
        ecs_entity_desc_t descriptor{};
        descriptor.name = name;
        return ecs_entity_init(world_, &descriptor);
    }

    template<typename T> ecs_entity_t component(const char *name) {
        ecs_component_desc_t descriptor{};
        descriptor.entity = entity(name);
        descriptor.type.size = sizeof(T);
        descriptor.type.alignment = alignof(T);
        const auto id = ecs_component_init(world_, &descriptor);
        if (!id) throw std::runtime_error("Flecs component registration failed");
        return id;
    }

    static void particles(ecs_iter_t *it) {
        auto *data = static_cast<bench::Particle *>(ecs_field_w_size(it, sizeof(bench::Particle), 0));
        for (int32_t i = 0; i < it->count; ++i) bench::step(data[i]);
    }

    static void wide(ecs_iter_t *it) {
        auto *data = static_cast<bench::Motion *>(ecs_field_w_size(it, sizeof(bench::Motion), 0));
        for (int32_t i = 0; i < it->count; ++i) bench::step(data[i]);
    }

    static void fly(ecs_iter_t *it) {
        auto *data = static_cast<bench::Bullet *>(ecs_field_w_size(it, sizeof(bench::Bullet), 0));
        for (int32_t i = 0; i < it->count; ++i) {
            if (bench::step(data[i])) ecs_delete(it->world, it->entities[i]);
        }
    }

    static void spawn(ecs_iter_t *it) {
        auto &self = *static_cast<Simulation *>(it->ctx);
        if (self.options_.workload == bench::Workload::churn) {
            for (std::uint32_t i = 0; i < self.options_.rate; ++i) {
                const auto b = bench::bullet(self.tick_, i);
                ecs_set_id(it->world, ecs_new(it->world), self.bullet_id_, sizeof(b), &b);
            }
            ++self.tick_;
            return;
        }
        if (self.ready_) return;
        self.ready_ = true;
        for (std::uint32_t i = 0; i < self.options_.count; ++i) {
            const auto e = ecs_new(it->world);
            if (self.options_.workload == bench::Workload::particles) {
                const auto p = bench::particle(i);
                ecs_set_id(it->world, e, self.particle_id_, sizeof(p), &p);
            } else {
                const auto m = bench::motion(i);
                ecs_set_id(it->world, e, self.motion_id_, sizeof(m), &m);
                if (self.options_.tagged && bench::hash_i2(i, 3) % 100 < self.options_.frozen) {
                    ecs_add_id(it->world, e, self.frozen_id_);
                }
            }
        }
    }

public:
    explicit Simulation(const bench::Options &o) : options_(o), world_(ecs_init()) {
        if (!world_) throw std::runtime_error("Flecs world initialization failed");
        particle_id_ = component<bench::Particle>("Particle");
        motion_id_ = component<bench::Motion>("Motion");
        bullet_id_ = component<bench::Bullet>("Bullet");
        frozen_id_ = entity("Frozen");

        const auto id = o.workload == bench::Workload::particles ? particle_id_ :
                        o.workload == bench::Workload::wide ? motion_id_ : bullet_id_;
        ecs_system_desc_t update{};
        update.entity = entity("Update");
        update.phase = EcsOnUpdate;
        update.query.cache_kind = EcsQueryCacheAll;
        update.query.terms[0].id = id;
        update.query.terms[0].inout = EcsInOut;
        if (o.workload == bench::Workload::wide && o.tagged) {
            update.query.terms[1].id = frozen_id_;
            update.query.terms[1].oper = EcsNot;
            update.query.terms[1].inout = EcsInOutNone;
        }
        update.callback = o.workload == bench::Workload::particles ? particles :
                          o.workload == bench::Workload::wide ? wide : fly;
        update.ctx = this;
        const auto update_id = ecs_system_init(world_, &update);
        if (!update_id) throw std::runtime_error("Flecs update system registration failed");

        // Same-phase systems are ordered by entity ID. Register Update first,
        // before any entity deletion: Fire/Setup then queues new entities after
        // old rows were updated, and ecs_progress includes the final merge.
        ecs_system_desc_t create{};
        create.entity = entity("Spawn");
        create.phase = EcsOnUpdate;
        create.query.terms[0].id = id;
        create.query.terms[0].inout = EcsOut;
        create.query.terms[0].src.id = EcsIsEntity; // [out] Component(): a task, not a row query
        create.callback = spawn;
        create.ctx = this;
        const auto create_id = ecs_system_init(world_, &create);
        if (!create_id || create_id <= update_id) throw std::runtime_error("Flecs spawn system order was not established");

        ecs_query_desc_t read{};
        read.terms[0].id = id;
        read.terms[0].inout = EcsIn;
        read.cache_kind = EcsQueryCacheAll;
        digest_query_ = ecs_query_init(world_, &read);
        if (!digest_query_) throw std::runtime_error("Flecs digest query registration failed");
    }

    ~Simulation() {
        if (digest_query_) ecs_query_fini(digest_query_);
        if (world_) ecs_fini(world_);
    }
    Simulation(const Simulation &) = delete;
    Simulation &operator=(const Simulation &) = delete;

    void tick() {
        if (!ecs_progress(world_, bench::dt)) throw std::runtime_error("Flecs pipeline unexpectedly stopped");
    }

    bench::Digest digest() {
        bench::Digest d;
        auto it = ecs_query_iter(world_, digest_query_);
        while (ecs_query_next(&it)) {
            switch (options_.workload) {
                case bench::Workload::particles: {
                    const auto *data = static_cast<const bench::Particle *>(ecs_field_w_size(&it, sizeof(bench::Particle), 0));
                    for (int32_t i = 0; i < it.count; ++i) d.sum += bench::item(data[i]);
                    break;
                }
                case bench::Workload::wide: {
                    const auto *data = static_cast<const bench::Motion *>(ecs_field_w_size(&it, sizeof(bench::Motion), 0));
                    for (int32_t i = 0; i < it.count; ++i) {
                        d.sum += bench::item(data[i]);
                        d.frozen += ecs_has_id(world_, it.entities[i], frozen_id_);
                    }
                    break;
                }
                case bench::Workload::churn: {
                    const auto *data = static_cast<const bench::Bullet *>(ecs_field_w_size(&it, sizeof(bench::Bullet), 0));
                    for (int32_t i = 0; i < it.count; ++i) d.sum += bench::item(data[i]);
                    break;
                }
            }
            d.count += static_cast<std::uint32_t>(it.count);
        }
        return d;
    }
};

int main(int argc, char **argv) {
    return bench::run<Simulation>(argc, argv, "Flecs", "4.1.6", "ecs_progress_cached_systems_table_storage");
}
