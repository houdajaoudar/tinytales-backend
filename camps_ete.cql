-- ============================================================
-- Projet UA3 : Conception d'une base de données Cassandra
-- Gestion des réservations des camps d'été pour enfants
-- ============================================================

-- Création du keyspace
CREATE KEYSPACE IF NOT EXISTS camps_ete
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

USE camps_ete;

-- ============================================================
-- TABLE 1 : Recherche des camps par type d'activité
-- Requête supportée : Trouver les camps disponibles selon le type
-- Partition key : type_activite
-- ============================================================
CREATE TABLE camps_par_type (
    type_activite       TEXT,
    id_camp             UUID,
    nom_camp            TEXT,
    localisation        TEXT,
    date_debut          DATE,
    date_fin            DATE,
    places_disponibles  INT,
    PRIMARY KEY (type_activite, id_camp)
);

-- ============================================================
-- TABLE 2 : Recherche des camps par localisation
-- Requête supportée : Trouver les camps disponibles selon la localisation
-- Partition key : localisation
-- ============================================================
CREATE TABLE camps_par_localisation (
    localisation        TEXT,
    id_camp             UUID,
    nom_camp            TEXT,
    type_activite       TEXT,
    date_debut          DATE,
    places_disponibles  INT,
    PRIMARY KEY (localisation, id_camp)
);

-- ============================================================
-- TABLE 3 : Consultation des camps par popularité
-- Requête supportée : Récupérer les camps selon leur popularité par année
-- Partition key : annee | Clustering key : nombre_inscriptions DESC
-- ============================================================
CREATE TABLE camps_par_popularite (
    annee               INT,
    nombre_inscriptions INT,
    id_camp             UUID,
    nom_camp            TEXT,
    type_activite       TEXT,
    localisation        TEXT,
    PRIMARY KEY (annee, nombre_inscriptions, id_camp)
) WITH CLUSTERING ORDER BY (nombre_inscriptions DESC, id_camp ASC);

-- ============================================================
-- TABLE 4 : Gestion des réservations par parent
-- Requête supportée : Organiser et réserver les camps pour les enfants
-- Partition key : id_parent | Clustering key : id_reservation DESC
-- ============================================================
CREATE TABLE reservations_par_parent (
    id_parent           UUID,
    id_reservation      UUID,
    id_enfant           UUID,
    nom_enfant          TEXT,
    id_camp             UUID,
    nom_camp            TEXT,
    date_reservation    TIMESTAMP,
    statut              TEXT,
    PRIMARY KEY (id_parent, id_reservation)
) WITH CLUSTERING ORDER BY (id_reservation DESC);

-- ============================================================
-- TABLE 5 : Gestion des paiements par réservation
-- Requête supportée : Payer pour inscrire officiellement les enfants
-- Partition key : id_reservation
-- ============================================================
CREATE TABLE paiements_par_reservation (
    id_reservation      UUID,
    id_paiement         UUID,
    montant             DECIMAL,
    date_paiement       TIMESTAMP,
    methode_paiement    TEXT,
    statut_paiement     TEXT,
    PRIMARY KEY (id_reservation, id_paiement)
);
