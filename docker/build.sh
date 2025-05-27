#!/bin/bash
# Official docker image build script.
#
CURDIR=`pwd`


usage() {
cat << EOF
usage: $0 options

OPTIONS:
   -t      The tag/version (${TAG}) (default = master)
   -r      Destroy and rebuild the buildx environment
EOF
}


ALL_PLATFORMS=0
DEV=0
REBUILD_BUILDX=0
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
        r)
           REBUILD_BUILDX=1
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
    PLATFORMS="linux/arm/v7"
fi

if [ $REBUILD_BUILDX -eq 1 ]
then
    echo "Destroying old multiarch build container"
    docker buildx rm multiarch
    docker run --rm --privileged multiarch/qemu-user-static --reset -p yes
    echo "Creating new buildx container"
    docker buildx create --name multiarch --driver docker-container --use \
        --config ./buildkit.toml --use \
        --driver-opt image=moby/buildkit:master
    docker buildx inspect --bootstrap
fi

echo "Build with tag=${TAG} BRANCH=${BRANCH} dev?=${DEV} platforms?=${PLATFORMS}"

echo "Build -DEV- with tag=${TAG} BRANCH=${BRANCH} platforms?=${PLATFORMS}"
#cd ../..
# Use this script to locally build the docker image
    #-f ./haminfo/docker/Dockerfile \
export BUILDKIT_PROGRESS=plain
docker buildx build --platform $PLATFORMS \
    -t hemna6969/haminfo:$TAG \
    -f ./Dockerfile \
    --build-arg branch=$BRANCH \
    --no-cache-filter \
    --progress=plain \
    --load .

#cd $CURDIR
