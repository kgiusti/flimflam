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

#define _GNU_SOURCE

#include <errno.h>
#include <netdb.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

#define BUFFER_SIZE 16384

typedef struct thread_context {
    int id;
    int socket;
    int port;
    char* output_dir;
} thread_context_t;

void* run_sender(void* data) {
    int sock = ((thread_context_t*) data)->socket;

    char* buffer = (char*) malloc(BUFFER_SIZE);
    memset(buffer, 'x', BUFFER_SIZE);

    while (1) {
        ssize_t sent = send(sock, buffer, BUFFER_SIZE, 0);
        if (sent < 0) break;
    }

    if (errno) {
        fprintf(stderr, "client: ERROR! %s\n", strerror(errno));
    }

    free(buffer);
}

void* run_receiver(void* data) {
    int id = ((thread_context_t*) data)->id;
    int sock = ((thread_context_t*) data)->socket;
    char* output_dir = ((thread_context_t*) data)->output_dir;

    char* buffer = (char*) malloc(BUFFER_SIZE);
    memset(buffer, 'x', BUFFER_SIZE);

    char transfers_file[256];
    snprintf(transfers_file, 256, "%s/transfers.%d.csv", output_dir, id);

    FILE* transfers = fopen(transfers_file, "w");
    if (!transfers) goto egress;

    size_t total_received = 0;

    while (1) {
        ssize_t received = recv(sock, buffer, BUFFER_SIZE / 4, MSG_WAITALL);
        if (received < 0) goto egress;

        if (received == 0) {
            printf("client: Disconnected\n");
            goto egress;
        }

        total_received += received;

        fprintf(transfers, "%d,%lu\n", received, total_received);
        fflush(transfers);
    }

egress:

    if (errno) {
        fprintf(stderr, "client: ERROR! %s\n", strerror(errno));
    }

    fclose(transfers);
    free(buffer);
}

int main(size_t argc, char** argv) {
    if (argc != 4) {
        fprintf(stderr, "Usage: client PORT JOBS OUTPUT-DIR\n");
        return 1;
    }

    int port = atoi(argv[1]);
    int jobs = atoi(argv[2]);
    char* output_dir = argv[3];

    pthread_t sender_threads[jobs];
    pthread_t receiver_threads[jobs];
    thread_context_t contexts[jobs];

    for (int i = 0; i < jobs; i++) {
        int sock = socket(AF_INET, SOCK_STREAM, 0);
        if (sock < 0) goto egress;

        contexts[i] = (thread_context_t) {
            .id = i,
            .socket = sock,
            .port = port,
            .output_dir = output_dir,
        };

        struct sockaddr_in addr = (struct sockaddr_in) {
            0,
            .sin_family = AF_INET,
            .sin_addr.s_addr = htonl(INADDR_LOOPBACK),
            .sin_port = htons(port)
        };

        printf("client: Connecting to port %d\n", port);

        int err = connect(sock, (const struct sockaddr*) &addr, sizeof(addr));
        if (err) goto egress;

        printf("client: Connected\n");

        pthread_create(&sender_threads[i], NULL, &run_sender, &contexts[i]);
        pthread_create(&receiver_threads[i], NULL, &run_receiver, &contexts[i]);

        pthread_setname_np(sender_threads[i], "sender");
        pthread_setname_np(receiver_threads[i], "receiver");
    }

    for (int i = 0; i < jobs; i++) {
        pthread_join(sender_threads[i], NULL);
        pthread_join(receiver_threads[i], NULL);
    }

egress:

    if (errno) {
        fprintf(stderr, "client: ERROR! %s\n", strerror(errno));
    }

    for (int i = 0; i < jobs; i++) {
        int sock = contexts[i].socket;
        if (sock > 0) close(sock);
    }

    exit(errno);
}
