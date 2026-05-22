(ns sample.core
  (:require [sample.db :as db]
            [clojure.string :as str]
            sample.audit)
  (:import [java.time Instant]))

(defonce default-role :guest)

(defrecord User [id name])

(defprotocol Store
  (fetch-user [this id]))

(defn normalize-name [name]
  (str/trim name))

(defn- enrich-user [user]
  (normalize-name (:name user)))

(defn quoted-example []
  '(normalize-name "quoted"))

(defn comment-example []
  (comment
    (normalize-name "commented"))
  nil)

(defmacro with-user [binding & body]
  `(let [~binding (fetch-current)]
     ~@body))

(defmulti render :type)

(defmethod render :user [user]
  (enrich-user user))

(defn handle-request [id]
  (let [user (db/fetch-user id)]
    (render (assoc user :name (normalize-name (:name user))))))
