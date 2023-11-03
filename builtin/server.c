/*
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied.  See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */

#include <errno.h>
#include <netdb.h>
#include <netinet/tcp.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

#define BUFFER_SIZE 16384

typedef struct thread_context {
    int socket;
} thread_context_t;

void* run(void* data) {
    int sock = ((thread_context_t*) data)->socket;
    char* buffer = (char*) malloc(BUFFER_SIZE);
    memset(buffer, 'y', BUFFER_SIZE);

    int opt = 1;
    int err = setsockopt(sock, IPPROTO_TCP, TCP_NODELAY, (void*) &opt, sizeof(opt));
    if (err) goto egress;

    while (1) {
        ssize_t received = recv(sock, buffer, BUFFER_SIZE / 4, 0);
        if (received < 0) goto egress;

        if (received == 0) {
            printf("server: Connection closed by peer\n");
            goto egress;
        }

        ssize_t sent = send(sock, buffer, BUFFER_SIZE, 0);
        if (sent < 0) goto egress;
    }

egress:

    if (errno) {
        fprintf(stderr, "server: ERROR! %s\n", strerror(errno));
    }

    close(sock);
    free(buffer);

    return NULL;
}

int main(size_t argc, char** argv) {
    if (argc != 2) {
        fprintf(stderr, "Usage: server PORT\n");
        return 1;
    }

    int port = atoi(argv[1]);

    int server_sock = socket(AF_INET, SOCK_STREAM, 0);
    if (server_sock < 0) goto egress;

    int opt = 1;
    int err = setsockopt(server_sock, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));
    if (err) goto egress;

    struct sockaddr_in addr = (struct sockaddr_in) {
        0,
        .sin_family = AF_INET,
        .sin_addr.s_addr = htonl(INADDR_LOOPBACK),
        .sin_port = htons(port)
    };

    err = bind(server_sock, (const struct sockaddr*) &addr, sizeof(addr));
    if (err) goto egress;

    err = listen(server_sock, 1);
    if (err) goto egress;

    printf("server: Listening for connections on port %d\n", port);

    while (1) {
        int sock = accept(server_sock, NULL, NULL);
        if (sock < 0) goto egress;

        printf("server: Connection accepted\n");

        pthread_t* thread = malloc(sizeof(pthread_t));
        thread_context_t* context = malloc(sizeof(thread_context_t));

        *context = (thread_context_t) {
            .socket = sock,
        };

        pthread_create(thread, NULL, &run, (void*) context);
    }

egress:

    if (errno) {
        fprintf(stderr, "server: ERROR! %s\n", strerror(errno));
    }

    if (server_sock > 0) {
        shutdown(server_sock, SHUT_RDWR);
    }

    return errno;
}
