#!/bin/bash
# Official docker image build script.


usage() {
cat << EOF
usage: $0 options

OPTIONS:
   -t      The tag/version (${TAG}) (default = master)
   -d      Use Dockerfile-dev for a git clone build
EOF
}


ALL_PLATFORMS=0
DEV=0
TAG="latest"
BRANCH="master"

while getopts “t:dab:” OPTION
do
    case $OPTION in
        t)
           TAG=$OPTARG
           ;;
        b)
           BRANCH=$OPTARG
           ;;
        a)
           ALL_PLATFORMS=1
           ;;
        d)
           DEV=1
           ;;
        ?)
           usage
           exit
           ;;
    esac
done

VERSION="2.3.1"

if [ $ALL_PLATFORMS -eq 1 ]
then
    PLATFORMS="linux/arm/v7,linux/arm/v6,linux/arm64,linux/amd64"
else
    PLATFORMS="linux/amd64"
fi

echo "Build with tag=${TAG} BRANCH=${BRANCH} dev?=${DEV} platforms?=${PLATFORMS}"


echo "Destroying old multiarch build container"
docker buildx rm multiarch
echo "Creating new buildx container"
docker buildx create --name multiarch --platform linux/arm/v7,linux/arm/v6,linux/arm64,linux/amd64 --config ./buildkit.toml --use --driver-opt image=moby/buildkit:master

    echo "Build -DEV- with tag=${TAG} BRANCH=${BRANCH} platforms?=${PLATFORMS}"
    # Use this script to locally build the docker image
    docker buildx build --platform $PLATFORMS \
        -t hemna6969/haminfo:$TAG \
        -f Dockerfile --build-arg branch=$BRANCH --no-cache .
