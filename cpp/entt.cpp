#include "common.hpp"

#include <entt/entt.hpp>

class Simulation {
    using Particle = bench::Particle;
    using Motion = bench::Motion;
    using Bullet = bench::Bullet;
    using Frozen = bench::Frozen;
    const bench::Options options_;
    entt::registry registry_;
    decltype(registry_.group<Motion>(entt::get<>, entt::exclude<Frozen>)) moving_;
    std::vector<Bullet> pending_spawns_;
    std::vector<entt::entity> spawn_entities_;
    std::vector<entt::entity> pending_deletes_;
    std::uint32_t tick_ = 0;
    bool ready_ = false;

    void setup() {
        for (std::uint32_t i = 0; i < options_.count; ++i) {
            const auto entity = registry_.create();
            if (options_.workload == bench::Workload::particles) {
                registry_.emplace<Particle>(entity, bench::particle(i));
            } else {
                registry_.emplace<Motion>(entity, bench::motion(i));
                if (options_.tagged && bench::hash_i2(i, 3) % 100 < options_.frozen) {
                    registry_.emplace<Frozen>(entity);
                }
            }
        }
    }

public:
    explicit Simulation(const bench::Options &o) : options_(o), moving_(registry_.group<Motion>(entt::get<>, entt::exclude<Frozen>)) {
        if (o.workload == bench::Workload::churn) {
            pending_spawns_.reserve(o.rate);
            spawn_entities_.resize(o.rate);
        }
    }

    void tick() {
        if (options_.workload != bench::Workload::churn && !ready_) {
            setup();
            ready_ = true;
            return;
        }
        switch (options_.workload) {
            case bench::Workload::particles:
                registry_.view<Particle>().each([](Particle &p) { bench::step(p); });
                break;
            case bench::Workload::wide:
                if (options_.tagged) moving_.each([](Motion &m) { bench::step(m); });
                else registry_.view<Motion>().each([](Motion &m) { bench::step(m); });
                break;
            case bench::Workload::churn:
                pending_spawns_.clear();
                pending_deletes_.clear();
                for (std::uint32_t i = 0; i < options_.rate; ++i) pending_spawns_.push_back(bench::bullet(tick_, i));
                ++tick_;
                registry_.view<Bullet>().each([this](entt::entity entity, Bullet &b) {
                    if (bench::step(b)) pending_deletes_.push_back(entity);
                });
                // Match deferred Fire/Fly visibility: newborn bullets do not move this tick.
                registry_.create(spawn_entities_.begin(), spawn_entities_.end());
                registry_.insert<Bullet>(spawn_entities_.begin(), spawn_entities_.end(), pending_spawns_.begin());
                registry_.destroy(pending_deletes_.begin(), pending_deletes_.end());
                break;
        }
    }

    bench::Digest digest() {
        bench::Digest d;
        switch (options_.workload) {
            case bench::Workload::particles:
                registry_.view<const Particle>().each([&d](const Particle &p) { d.sum += bench::item(p); ++d.count; });
                break;
            case bench::Workload::wide:
                registry_.view<const Motion>().each([this, &d](entt::entity e, const Motion &m) {
                    d.sum += bench::item(m);
                    ++d.count;
                    d.frozen += registry_.all_of<Frozen>(e);
                });
                break;
            case bench::Workload::churn:
                registry_.view<const Bullet>().each([&d](const Bullet &b) { d.sum += bench::item(b); ++d.count; });
                break;
        }
        return d;
    }
};

int main(int argc, char **argv) {
    return bench::run<Simulation>(argc, argv, "EnTT", "4.0.0", "explicit_tick_views_and_owning_filtered_group");
}
