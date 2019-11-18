#!/bin/bash
# install minikube on CI
# this sets up minikube with vm-driver=none, so should not be used anywhere but CI
set -eux

mkdir -p bin $HOME/.kube $HOME/.minikube
touch $KUBECONFIG

# install kubectl, minikube
# based on https://github.com/LiliC/travis-minikube
echo "installing kubectl"
curl -Lo kubectl https://storage.googleapis.com/kubernetes-release/release/v${KUBE_VERSION}/bin/linux/amd64/kubectl
chmod +x kubectl
mv kubectl bin/

echo "installing minikube"
curl -Lo minikube https://storage.googleapis.com/minikube/releases/v${MINIKUBE_VERSION}/minikube-linux-amd64
chmod +x minikube
mv minikube bin/

echo "starting minikube"
sudo $PWD/bin/minikube start --vm-driver=none --kubernetes-version=v${KUBE_VERSION}
sudo chown -R travis: /home/travis/.minikube/
minikube update-context


# can be used to check a condition of nodes and pods
JSONPATH='{range .items[*]}{@.metadata.name}:{range @.status.conditions[*]}{@.type}={@.status};{end}{end}'

echo "waiting for kube-addon-manager"
until kubectl -n kube-system get pods -l component=kube-addon-manager -o jsonpath="$JSONPATH" 2>&1 | grep -q "Ready=True"; do
  sleep 1
done

echo "waiting for kube-dns"
until kubectl -n kube-system get pods -l k8s-app=kube-dns -o jsonpath="$JSONPATH" 2>&1 | grep -q "Ready=True"; do
  sleep 1
done

kubectl get nodes
kubectl get pods --all-namespaces
