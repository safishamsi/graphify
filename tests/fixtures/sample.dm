#include "helpers.dm"

var/global_counter = 0

/proc/log_event(msg)
	world.log << msg
	global_counter++

/datum/weapon
	var/damage = 10
	var/name = "weapon"

	proc/attack(mob/target)
		log_event("attack")
		target.take_damage(damage)
		return damage

	New()
		log_event("weapon created")

/datum/weapon/sword
	damage = 20
	name = "sword"

/datum/weapon/sword/proc/sharpen()
	damage += 5
	log_event("sharpened")

/datum/weapon/sword/attack(mob/target)
	sharpen()
	return ..()

/proc/RunTest()
	var/datum/weapon/sword/s = new /datum/weapon/sword()
	s.attack(null)
