# One Dockerfile for every Go service:  docker build --build-arg SERVICE=orders-svc --build-arg GIT_SHA=$(git rev-parse --short HEAD) .
FROM golang:1.22 AS build
WORKDIR /src
COPY go.mod ./
COPY internal ./internal
COPY orders-svc ./orders-svc
COPY payments-svc ./payments-svc
COPY stubs ./stubs
RUN go mod tidy
ARG SERVICE
ARG GIT_SHA=dev
ARG BUG=
RUN CGO_ENABLED=0 go build -ldflags "-X main.version=${GIT_SHA} -X main.bug=${BUG}" -o /out/svc ./${SERVICE}

FROM gcr.io/distroless/static-debian12
COPY --from=build /out/svc /svc
ENTRYPOINT ["/svc"]
