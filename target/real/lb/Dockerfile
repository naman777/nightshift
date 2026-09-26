# The REAL C++ load balancer (external/load-balancer, github.com/naman777/Load-Balancer-CPP) as the `lb` service.
# Built by docker-compose.real.yml with the balancer source passed as the additional build context `lbsrc`.
FROM gcc:13 AS build
COPY --from=lbsrc load-balancer /src/load-balancer
# static libstdc++/libgcc so the binary runs on a slim runtime image
RUN make -C /src/load-balancer clean && make -C /src/load-balancer load_balancer CXXFLAGS="-std=c++17 -pthread -O2 -static-libstdc++ -static-libgcc"

FROM debian:bookworm-slim
COPY --from=build /src/load-balancer/load_balancer /usr/local/bin/load_balancer
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
EXPOSE 8080 8081
ENTRYPOINT ["/entrypoint.sh"]
